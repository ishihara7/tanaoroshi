plugins {
    id("com.android.application")
}

android {
    namespace = "jp.co.ryomo.tanaoroshi.ar"
    compileSdk = 37

    defaultConfig {
        applicationId = "jp.co.ryomo.tanaoroshi.ar"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.2"
    }
}

dependencies {
    implementation("com.google.ar:core:1.57.0")
    implementation("com.google.zxing:core:3.5.3") // QRの読み取り（ARCoreのカメラ画像から）
    testImplementation("junit:junit:4.13.2")
}
