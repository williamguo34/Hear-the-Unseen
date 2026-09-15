using Apple.PHASE;
using UnityEngine;

namespace ForceSense
{
    public static class SpatialAudio
    {
        public static PHASEListener ConfigureListener(GameObject head)
        {
            if (head.GetComponent<AudioListener>() == null)
                head.AddComponent<AudioListener>();

            var listener = head.GetComponent<PHASEListener>();
            if (listener == null)
                listener = head.AddComponent<PHASEListener>();

            listener.SetAutomaticListenerHeadTracking(false);
            listener.SetReverbPreset(Helpers.ReverbPresets.None);
            return listener;
        }

        public static void ConfigurePointSource(AudioSource source, bool filterBeforeSpatialize = false)
        {
            source.spatialBlend = 1f;
            source.spatialize = true;
            source.spatializePostEffects = filterBeforeSpatialize;
            source.dopplerLevel = 0.12f;
            source.rolloffMode = AudioRolloffMode.Linear;
            source.minDistance = 0.25f;
            source.maxDistance = 12f;
            source.playOnAwake = false;
            source.reverbZoneMix = 0f;
        }

        public static AudioSource LoopOn(GameObject host, AudioClip clip, float volume, bool filterBeforeSpatialize = false)
        {
            var source = host.AddComponent<AudioSource>();
            ConfigurePointSource(source, filterBeforeSpatialize);
            source.clip = clip;
            source.loop = true;
            source.volume = volume;
            if (clip != null) source.Play();
            return source;
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
