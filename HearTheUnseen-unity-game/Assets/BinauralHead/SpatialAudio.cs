using UnityEngine;

namespace HearTheUnseen
{
    public static class SpatialAudio
    {
        public static void ConfigureListener(GameObject head)
        {
            if (head.GetComponent<AudioListener>() == null)
                head.AddComponent<AudioListener>();

            var listener = head.GetComponent<SteamAudio.SteamAudioListener>();
            if (listener == null)
            {
                listener = head.AddComponent<SteamAudio.SteamAudioListener>();
                listener.applyReverb = Settings().applyListenerReverb;
            }

            if (head.GetComponent<HeadListenerAnchor>() == null)
                head.AddComponent<HeadListenerAnchor>();

            BindListener(head.transform);
        }

        public static void BindListener(Transform head)
        {
            if (head == null || SteamAudio.SteamAudioManager.Singleton == null) return;
            SteamAudio.SteamAudioManager.NotifyAudioListenerChangedTo(head);
        }

        public static void ConfigurePointSource(AudioSource source, bool filterBeforeSpatialize = false)
        {
            var mix = Settings();
            source.spatialBlend = 1f;
            source.spatialize = true;
            source.spatializePostEffects = filterBeforeSpatialize;
            source.dopplerLevel = mix.dopplerLevel;
            source.rolloffMode = mix.rolloffMode;
            source.minDistance = mix.minDistance;
            source.maxDistance = mix.maxDistance;
            source.playOnAwake = false;
            source.reverbZoneMix = mix.reverbZoneMix;

            var steam = source.GetComponent<SteamAudio.SteamAudioSource>();
            if (steam == null)
                steam = source.gameObject.AddComponent<SteamAudio.SteamAudioSource>();
            steam.directBinaural = mix.directBinaural;
            steam.interpolation = mix.interpolation;
            steam.perspectiveCorrection = mix.perspectiveCorrection;
            steam.distanceAttenuation = mix.distanceAttenuation;
            steam.airAbsorption = mix.airAbsorption;
            steam.directivity = mix.directivity;
            steam.occlusion = mix.occlusion;
            steam.transmission = mix.transmission;
            steam.reflections = mix.reflections;
            steam.pathing = mix.pathing;
            steam.directMixLevel = mix.directMixLevel;
        }

        static SpatialMixSettings _fallback;

        static SpatialMixSettings Settings()
        {
            var loaded = SpatialMixSettings.Current;
            if (loaded != null) return loaded;
            if (_fallback == null) _fallback = ScriptableObject.CreateInstance<SpatialMixSettings>();
            return _fallback;
        }

        public static void PlayOneShotAt(AudioClip clip, Vector3 position, float volume, float pitch)
        {
            if (clip == null) return;
            var go = new GameObject("FeedbackSource");
            go.transform.position = position;
            var source = go.AddComponent<AudioSource>();
            ConfigurePointSource(source);
            source.clip = clip;
            source.volume = volume;
            source.pitch = pitch;
            source.Play();
            Object.Destroy(go, clip.length / Mathf.Max(0.08f, pitch) + 0.05f);
        }
    }
}
