plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
 namespace="com.fujiroadtrip.batterybridge"; compileSdk=35
 defaultConfig { applicationId="com.fujiroadtrip.batterybridge"; minSdk=26; targetSdk=35; versionCode=1; versionName="0.1" }
}
kotlinOptions { jvmTarget="17" }
