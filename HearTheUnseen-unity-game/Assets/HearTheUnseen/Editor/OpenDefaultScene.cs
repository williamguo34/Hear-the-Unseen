using UnityEditor;
using UnityEditor.SceneManagement;

namespace HearTheUnseen.Editor
{
    [InitializeOnLoad]
    static class OpenDefaultScene
    {
        const string ScenePath = "Assets/HearTheUnseen/Scenes/HearTheUnseen.unity";

        static OpenDefaultScene()
        {
            EditorApplication.delayCall += OpenIfUntitled;
        }

        static void OpenIfUntitled()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling) return;
            var scene = EditorSceneManager.GetActiveScene();
            if (!string.IsNullOrEmpty(scene.path) || scene.isDirty) return;
            if (!System.IO.File.Exists(ScenePath)) return;
            EditorSceneManager.OpenScene(ScenePath);
        }
    }
}
