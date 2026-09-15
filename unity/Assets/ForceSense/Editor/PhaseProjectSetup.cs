using UnityEditor;
using UnityEngine;

namespace ForceSense.Editor
{
    [InitializeOnLoad]
    public static class PhaseProjectSetup
    {
        const string Spatializer = "PHASE Spatializer";

        static PhaseProjectSetup()
        {
            EditorApplication.delayCall += Apply;
        }

        [MenuItem("ForceSense/Use PHASE Spatializer")]
        public static void Apply()
        {
            var assets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/AudioManager.asset");
            if (assets == null || assets.Length == 0) return;
            var so = new SerializedObject(assets[0]);
            var plugin = so.FindProperty("m_SpatializerPlugin");
            if (plugin == null || plugin.stringValue == Spatializer) return;
            plugin.stringValue = Spatializer;
            so.ApplyModifiedProperties();
            Debug.Log("ForceSense: Audio spatializer set to PHASE Spatializer.");
        }
    }
}
