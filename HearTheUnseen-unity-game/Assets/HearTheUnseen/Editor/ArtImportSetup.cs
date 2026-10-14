using UnityEditor;
using UnityEngine;

namespace HearTheUnseen.Editor
{
    public sealed class ArtImportSetup : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            if (!assetPath.Contains("HearTheUnseen/Resources/Art")) return;
            var importer = (TextureImporter)assetImporter;
            if (assetPath.Contains("/Vfx/"))
            {
                importer.textureType = TextureImporterType.Default;
                importer.alphaIsTransparency = true;
                importer.mipmapEnabled = false;
                importer.wrapMode = TextureWrapMode.Clamp;
                importer.npotScale = TextureImporterNPOTScale.None;
                return;
            }

            if (assetPath.Contains("_nor"))
            {
                importer.textureType = TextureImporterType.NormalMap;
                importer.sRGBTexture = false;
                return;
            }

            importer.textureType = TextureImporterType.Default;
            importer.sRGBTexture = !assetPath.Contains("rough");
        }
    }
}
