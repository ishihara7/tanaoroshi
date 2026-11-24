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
        versionName = "0.1"
    }
}

dependencies {
    implementation("com.google.ar:core:1.57.0")
}
