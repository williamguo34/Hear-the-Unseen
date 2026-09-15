using SteamAudio;
using UnityEditor;
using UnityEditor.Build;
using UnityEngine;

namespace ForceSense.Editor
{
    [InitializeOnLoad]
    public static class SteamAudioProjectSetup
    {
        const string Spatializer = "Steam Audio Spatializer";
        const string Ambisonic = "Steam Audio Ambisonic Decoder";
        const string Define = "STEAMAUDIO_ENABLED";

        static SteamAudioProjectSetup()
        {
            EditorApplication.delayCall += Apply;
        }

        [MenuItem("ForceSense/Use Steam Audio Spatializer")]
        public static void Apply()
        {
            ApplyAudioPlugins();
            ApplyScriptingDefine();
            ApplySteamAudioSettings();
        }

        static void ApplyAudioPlugins()
        {
            var assets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/AudioManager.asset");
            if (assets == null || assets.Length == 0) return;
            var so = new SerializedObject(assets[0]);
            var plugin = so.FindProperty("m_SpatializerPlugin");
            var ambisonic = so.FindProperty("m_AmbisonicDecoderPlugin");
            var dirty = false;
            if (plugin != null && plugin.stringValue.Trim() != Spatializer)
            {
                plugin.stringValue = Spatializer;
                dirty = true;
            }
            if (ambisonic != null && ambisonic.stringValue.Trim() != Ambisonic)
            {
                ambisonic.stringValue = Ambisonic;
                dirty = true;
            }
            if (!dirty) return;
            so.ApplyModifiedProperties();
            Debug.Log("ForceSense: Audio spatializer set to Steam Audio Spatializer.");
        }

        static void ApplyScriptingDefine()
        {
            EnsureDefine(NamedBuildTarget.Standalone);
        }

        static void EnsureDefine(NamedBuildTarget target)
        {
            var defines = PlayerSettings.GetScriptingDefineSymbols(target);
            var parts = string.IsNullOrEmpty(defines) ? new string[0] : defines.Split(';');
            for (var i = 0; i < parts.Length; i++)
            {
                if (parts[i] == Define) return;
            }
            PlayerSettings.SetScriptingDefineSymbols(
                target,
                string.IsNullOrEmpty(defines) ? Define : defines + ";" + Define);
        }

        static void ApplySteamAudioSettings()
        {
            var settings = SteamAudioSettings.Singleton;
            if (settings == null) return;
            if (!settings.perspectiveCorrection && !settings.hrtfDisabled) return;
            settings.perspectiveCorrection = false;
            settings.hrtfDisabled = false;
            EditorUtility.SetDirty(settings);
        }
    }
}
