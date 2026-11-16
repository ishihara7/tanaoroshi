"""管理者向け：備品のCSV取込、台帳・位置履歴のCSV出力。"""
import csv
import io

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import Asset, Scan, User
from app.routers.admin_assets import _new_token, tag_url
from app.services.assets import ASSET_NO_RE, ASSET_NO_RULE
from app.templating import jst, templates

router = APIRouter()

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
IMPORT_COLUMNS = ["管理番号", "名称", "備考"]


def csv_safe(value):
    """Excelで開いたときに、数式として実行されないようにする（CSVインジェクション対策）。"""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def csv_response(filename: str, header: list[str], rows) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(v) for v in r])
    # Excelで文字化けしないよう、BOM付きUTF-8にする
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp932")  # Excelの「CSV（コンマ区切り）」で保存した場合


def _import_page(request, user, *, result=None, error=None, status=200):
    return templates.TemplateResponse(request, "admin_import.html", {
        "user": user, "result": result, "error": error, "columns": IMPORT_COLUMNS}, status_code=status)


@router.get("/admin/assets-import", response_class=HTMLResponse)
def import_page(request: Request, user: User = Depends(auth.require_admin)):
    return _import_page(request, user)


@router.post("/admin/assets-import")
def import_run(request: Request, file: UploadFile = File(...), csrf_token: str = Form(""),
               user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    if not auth.check_csrf(request, csrf_token):
        return _import_page(request, user, error="画面の有効期限が切れました。もう一度お試しください。", status=400)
    data = file.file.read(MAX_CSV_BYTES + 1)
    if not data:
        return _import_page(request, user, error="CSVファイルを選んでください。", status=400)
    if len(data) > MAX_CSV_BYTES:
        return _import_page(request, user, error="ファイルは2MB以下にしてください。", status=400)
    try:
        text = _decode(data)
    except UnicodeDecodeError:
        return _import_page(request, user, error="文字コードを判別できません。UTF-8 または Shift_JIS で保存してください。", status=400)

    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in ("管理番号", "名称") if c not in headers]
    if missing:
        return _import_page(request, user, error="1行目の見出しに「" + "」「".join(missing) + "」がありません。", status=400)

    ignored = [h for h in headers if h and h not in IMPORT_COLUMNS]  # 使わない列（結果に表示する）
    existing = {n.upper() for n in session.scalars(select(Asset.asset_no))}  # 大文字・小文字を区別しない
    to_add, skipped, errors, seen = [], [], [], set()
    for i, raw in enumerate(reader, start=2):  # 見出しが1行目
        if len(to_add) + len(skipped) + len(errors) >= MAX_ROWS:
            errors.append((i, "行数が多すぎます（1,000行まで）。ファイルを分けてください。"))
            break
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        if not any(row.values()):
            continue  # 空行
        no, name, note = row.get("管理番号", ""), row.get("名称", ""), row.get("備考", "")
        if not ASSET_NO_RE.fullmatch(no):
            errors.append((i, f"管理番号「{no}」は、{ASSET_NO_RULE}ではありません（Excelで、先頭の0が消えていないかも確認してください）。"))
        elif not (1 <= len(name) <= 100) or len(note) > 500:
            errors.append((i, "名称は1〜100文字、備考は500文字以内にしてください。"))
        elif no.upper() in existing or no.upper() in seen:
            skipped.append((i, no))
        else:
            seen.add(no.upper())
            to_add.append((no, name, note))

    if errors:  # 1件でも誤りがあれば、何も登録しない（直して、もう一度取り込めるようにする）
        return _import_page(request, user, result={"added": 0, "skipped": skipped, "errors": errors, "rolled_back": True, "ignored": ignored}, status=400)
    for no, name, note in to_add:
        session.add(Asset(asset_no=no, name=name, note=note, tag_token=_new_token(session)))
        session.flush()
    session.commit()
    return _import_page(request, user, result={"added": len(to_add), "skipped": skipped, "errors": [], "rolled_back": False, "ignored": ignored})


@router.get("/admin/export/assets.csv")
def export_assets(request: Request, user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    rows = [
        (a.asset_no, a.name, a.note, "使用中" if a.is_active else "廃棄",
         jst(a.last_seen_at), a.current_lat, a.current_lon, a.current_accuracy_m, tag_url(request, a.tag_token))
        for a in session.scalars(select(Asset).order_by(Asset.asset_no))
    ]
    return csv_response("assets.csv", ["管理番号", "名称", "備考", "状態", "最後の確認", "緯度", "経度", "誤差m", "タグURL"], rows)


@router.get("/admin/export/scans.csv")
def export_scans(user: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    q = (select(Scan, Asset.name)
         .join(Asset, Asset.asset_no == Scan.asset_no, isouter=True).order_by(Scan.id))
    # 記録者は、社員番号だけ（氏名・アカウント名は出さない）
    rows = [(jst(s.created_at, "%Y-%m-%d %H:%M:%S"), s.asset_no, aname or "", s.employee_no or "",
             s.latitude, s.longitude, s.accuracy_m, s.altitude, s.error_message)
            for s, aname in session.execute(q).all()]
    return csv_response("scans.csv", ["日時", "管理番号", "名称", "社員番号", "緯度", "経度", "誤差m", "高度", "エラー"], rows)
