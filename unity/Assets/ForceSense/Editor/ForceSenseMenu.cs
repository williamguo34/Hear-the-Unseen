using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace ForceSense.Editor
{
    public static class ForceSenseMenu
    {
        [MenuItem("ForceSense/Build Scene")]
        public static void BuildScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            ForceSenseBootstrap.Build();
            System.IO.Directory.CreateDirectory("Assets/ForceSense/Scenes");
            EditorSceneManager.SaveScene(scene, "Assets/ForceSense/Scenes/ForceSense.unity");
            EditorBuildSettings.scenes = new[]
            {
                new EditorBuildSettingsScene("Assets/ForceSense/Scenes/ForceSense.unity", true)
            };
            Debug.Log("ForceSense scene saved to Assets/ForceSense/Scenes/ForceSense.unity");
        }
    }
}
