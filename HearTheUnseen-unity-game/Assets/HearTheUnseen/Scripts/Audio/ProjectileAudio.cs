using UnityEngine;

namespace HearTheUnseen
{
    public sealed class ProjectileAudio : MonoBehaviour
    {
        const float DistanceMin = 0.3f;
        const float DistanceMax = 3f;

        [SerializeField] AudioSource farSource;
        [SerializeField] AudioSource nearSource;
        [SerializeField] AudioLowPassFilter lowPass;

        float _modPhase;

        public void Begin()
        {
            _modPhase = 0f;
            ApplyMix();
            Play(farSource);
            Play(nearSource);
        }

        public void Tick(Vector3 projectile, Vector3 listener)
        {
            if (farSource == null) return;
            var q = 1f - Mathf.Clamp01((Vector3.Distance(projectile, listener) - DistanceMin) / (DistanceMax - DistanceMin));
            var fMod = 2f + 10f * q;
            _modPhase += fMod * Time.deltaTime;
            var pulse = 0.58f + 0.42f * (0.5f + 0.5f * Mathf.Sin(_modPhase * Mathf.PI * 2f));

            farSource.volume = (0.20f + 0.42f * q) * pulse;
            farSource.pitch = 0.96f + 0.08f * q;
            if (nearSource != null)
            {
                nearSource.volume = (0.04f + 0.58f * q) * pulse;
                nearSource.pitch = 0.98f + 0.10f * q;
            }
            if (lowPass != null)
                lowPass.cutoffFrequency = Mathf.Lerp(850f, 7200f, q);
        }

        public void End()
        {
            if (farSource != null) farSource.Stop();
            if (nearSource != null) nearSource.Stop();
            _modPhase = 0f;
        }

        void ApplyMix()
        {
            if (farSource != null) SpatialAudio.ConfigurePointSource(farSource, filterBeforeSpatialize: true);
            if (nearSource != null) SpatialAudio.ConfigurePointSource(nearSource, filterBeforeSpatialize: true);
        }

        static void Play(AudioSource source)
        {
            if (source != null && source.clip != null) source.Play();
        }
    }
}
