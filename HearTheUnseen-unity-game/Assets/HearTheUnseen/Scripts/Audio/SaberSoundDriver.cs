using UnityEngine;

namespace HearTheUnseen
{
    public sealed class SaberSoundDriver : MonoBehaviour
    {
        public TrackedSaberController Saber;

        [SerializeField] float omega0 = 1f;
        [SerializeField] float omega1 = 8f;
        [SerializeField] float humVolume = 0.18f;
        [SerializeField] float humDoppler = 0.04f;
        [SerializeField] float whooshVolume = 0.62f;
        [SerializeField] AudioSource hum;
        [SerializeField] AudioSource whooshLow;
        [SerializeField] AudioSource whooshMid;
        [SerializeField] AudioSource whooshFast;

        float _speed01;
        float _humGain;

        public void Bind(AudioBank bank)
        {
            if (bank != null)
            {
                Fill(hum, bank.SaberHum);
                Fill(whooshLow, bank.SwingLow);
                Fill(whooshMid, bank.SwingMid);
                Fill(whooshFast, bank.SwingFast);
            }
            ApplyMix();
            PlayLoops();
        }

        void Start() => Bind(null);

        void Update()
        {
            var live = Saber != null && Saber.PoseValid;
            var targetHum = live ? humVolume : 0f;
            _humGain = Mathf.MoveTowards(_humGain, targetHum, Time.deltaTime * 2.4f);
            if (hum != null) hum.volume = _humGain;

            var omega = live ? Saber.AngularSpeedRadS : 0f;
            var s = Mathf.Clamp01((omega - omega0) / Mathf.Max(0.01f, omega1 - omega0));
            _speed01 = Mathf.Lerp(_speed01, s, 1f - Mathf.Exp(-14f * Time.deltaTime));

            var gain = whooshVolume * _speed01;
            var pitch = 0.9f + 0.25f * _speed01;
            SetWhoosh(whooshLow, Band(_speed01, 0.12f, 0.42f) * gain, pitch);
            SetWhoosh(whooshMid, Band(_speed01, 0.50f, 0.40f) * gain, pitch);
            SetWhoosh(whooshFast, Band(_speed01, 1.00f, 0.46f) * gain, pitch);
        }

        void ApplyMix()
        {
            if (hum != null)
            {
                SpatialAudio.ConfigurePointSource(hum);
                hum.dopplerLevel = humDoppler;
            }
            if (whooshLow != null) SpatialAudio.ConfigurePointSource(whooshLow);
            if (whooshMid != null) SpatialAudio.ConfigurePointSource(whooshMid);
            if (whooshFast != null) SpatialAudio.ConfigurePointSource(whooshFast);
        }

        void PlayLoops()
        {
            Play(hum);
            Play(whooshLow);
            Play(whooshMid);
            Play(whooshFast);
        }

        static void Fill(AudioSource source, AudioClip clip)
        {
            if (source != null && source.clip == null) source.clip = clip;
        }

        static void Play(AudioSource source)
        {
            if (source != null && source.clip != null && !source.isPlaying) source.Play();
        }

        static float Band(float s, float center, float width)
        {
            return Mathf.Clamp01(1f - Mathf.Abs(s - center) / width);
        }

        static void SetWhoosh(AudioSource source, float volume, float pitch)
        {
            if (source == null) return;
            source.volume = volume;
            source.pitch = pitch;
        }
    }
}
