using UnityEngine;

namespace HearTheUnseen
{
    [CreateAssetMenu(fileName = "SpatialMix", menuName = "Hear the Unseen/Spatial Mix")]
    public sealed class SpatialMixSettings : ScriptableObject
    {
        [Header("Unity AudioSource")]
        public float dopplerLevel = 0.12f;
        public AudioRolloffMode rolloffMode = AudioRolloffMode.Linear;
        public float minDistance = 0.25f;
        public float maxDistance = 12f;
        [Range(0f, 1.1f)] public float reverbZoneMix = 0f;

        [Header("Steam Audio listener")]
        [Tooltip("Head listener only. Leave off. Head pose is the listener.")]
        public bool applyListenerReverb = false;

        [Header("Steam Audio source")]
        public bool directBinaural = true;
        public SteamAudio.HRTFInterpolation interpolation = SteamAudio.HRTFInterpolation.Bilinear;
        public bool perspectiveCorrection = false;
        [Tooltip("Off so this does not stack on the Unity rolloff above.")]
        public bool distanceAttenuation = false;
        public bool airAbsorption = false;
        public bool directivity = false;
        public bool occlusion = false;
        public bool transmission = false;
        public bool reflections = false;
        public bool pathing = false;
        [Range(0f, 1f)] public float directMixLevel = 1f;

        static SpatialMixSettings _current;

        public static SpatialMixSettings Current
        {
            get
            {
                if (_current != null) return _current;
                var loaded = Resources.Load<SpatialMixSettings>("SpatialMix");
                if (loaded != null) _current = loaded;
                return _current;
            }
        }
    }
}
