plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "jp.co.ryomo.tanaoroshi.ar"
    compileSdk = 37

    defaultConfig {
        applicationId = "jp.co.ryomo.tanaoroshi.ar"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.3"
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation("com.google.ar:core:1.57.0")
    implementation("com.google.zxing:core:3.5.3") // QRの読み取り（ARCoreのカメラ画像から）
    val composeBom = platform("androidx.compose:compose-bom:2025.10.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.11.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
}
