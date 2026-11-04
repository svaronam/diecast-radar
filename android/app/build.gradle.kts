plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.svaronam.diecastradar"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.svaronam.diecastradar"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    // Clave fija: así cada APK nueva se instala encima de la anterior sin desinstalar.
    signingConfigs {
        create("radar") {
            storeFile = file("radar.keystore")
            storePassword = System.getenv("KEYSTORE_PASSWORD")
            keyAlias = "radar"
            keyPassword = System.getenv("KEYSTORE_PASSWORD")
        }
    }

    buildTypes {
        getByName("debug") {
            signingConfig = signingConfigs.getByName("radar")
        }
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("radar")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }
}
