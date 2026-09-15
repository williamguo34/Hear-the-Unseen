using UnityEngine;

namespace ForceSense
{
    public sealed class SaberSoundDriver : MonoBehaviour
    {
        public TrackedSaberController Saber;

        [SerializeField] float omega0 = 1f;
        [SerializeField] float omega1 = 8f;
        [SerializeField] float humVolume = 0.18f;
        [SerializeField] float whooshVolume = 0.62f;

        AudioSource _hum;
        AudioSource _low;
        AudioSource _mid;
        AudioSource _fast;
        float _speed01;
        float _humGain;

        public void Bind(AudioBank bank)
        {
            if (bank == null) return;
            _hum = SpatialAudio.LoopOn(gameObject, bank.SaberHum, 0f);
            if (_hum != null) _hum.dopplerLevel = 0.04f;

            var blade = new GameObject("Whoosh");
            blade.transform.SetParent(transform, false);
            blade.transform.localPosition = new Vector3(0f, 0f, TrackedSaberController.BladeLengthM * 0.45f);
            _low = SpatialAudio.LoopOn(blade, bank.SwingLow, 0f);
            _mid = SpatialAudio.LoopOn(blade, bank.SwingMid, 0f);
            _fast = SpatialAudio.LoopOn(blade, bank.SwingFast, 0f);
        }

        void Update()
        {
            var live = Saber != null && Saber.PoseValid;
            var targetHum = live ? humVolume : 0f;
            _humGain = Mathf.MoveTowards(_humGain, targetHum, Time.deltaTime * 2.4f);
            if (_hum != null) _hum.volume = _humGain;

            var omega = live ? Saber.AngularSpeedRadS : 0f;
            var s = Mathf.Clamp01((omega - omega0) / Mathf.Max(0.01f, omega1 - omega0));
            _speed01 = Mathf.Lerp(_speed01, s, 1f - Mathf.Exp(-14f * Time.deltaTime));

            var gain = whooshVolume * _speed01;
            var pitch = 0.9f + 0.25f * _speed01;
            SetWhoosh(_low, Band(_speed01, 0.12f, 0.42f) * gain, pitch);
            SetWhoosh(_mid, Band(_speed01, 0.50f, 0.40f) * gain, pitch);
            SetWhoosh(_fast, Band(_speed01, 1.00f, 0.46f) * gain, pitch);
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
