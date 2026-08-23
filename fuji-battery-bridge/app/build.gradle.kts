plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.fujiroadtrip.batterybridge"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.fujiroadtrip.batterybridge"
        minSdk = 26
        targetSdk = 35
        versionCode = 3
        versionName = "0.3"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}
