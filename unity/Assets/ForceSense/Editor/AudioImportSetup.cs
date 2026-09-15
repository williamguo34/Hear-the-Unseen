using UnityEditor;
using UnityEngine;

namespace ForceSense.Editor
{
    public sealed class AudioImportSetup : AssetPostprocessor
    {
        void OnPreprocessAudio()
        {
            if (!assetPath.Contains("ForceSense/Resources/Audio")) return;
            var importer = (AudioImporter)assetImporter;
            importer.forceToMono = true;
            importer.loadInBackground = false;
            var settings = importer.defaultSampleSettings;
            settings.loadType = AudioClipLoadType.DecompressOnLoad;
            settings.compressionFormat = AudioCompressionFormat.PCM;
            settings.quality = 1f;
            importer.defaultSampleSettings = settings;
        }
    }
}
