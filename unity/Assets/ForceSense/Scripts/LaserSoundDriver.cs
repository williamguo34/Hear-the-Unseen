using UnityEngine;

namespace ForceSense
{
    public sealed class LaserSoundDriver : MonoBehaviour
    {
        const float DistanceMin = 0.3f;
        const float DistanceMax = 3f;

        AudioBank _bank;
        AudioSource _far;
        AudioSource _near;
        AudioLowPassFilter _lpf;
        float _modPhase;

        public void Bind(AudioBank bank)
        {
            _bank = bank;
        }

        public void PlayLaunch(Vector3 origin)
        {
            if (_bank == null) return;
            SpatialAudio.PlayOneShotAt(_bank.Pick(_bank.Launch), origin, 0.48f, Random.Range(0.96f, 1.04f));
        }

        public void StartIncoming(Transform source)
        {
            StopIncoming();
            if (_bank == null || source == null) return;

            var farGo = Child(source, "IncomingFar");
            _far = SpatialAudio.LoopOn(farGo, _bank.Incoming, 0.2f, filterBeforeSpatialize: true);
            _lpf = farGo.AddComponent<AudioLowPassFilter>();
            _lpf.cutoffFrequency = 850f;
            _lpf.lowpassResonanceQ = 1f;

            var nearGo = Child(source, "IncomingNear");
            _near = SpatialAudio.LoopOn(nearGo, _bank.IncomingNear, 0f, filterBeforeSpatialize: true);
        }

        public void UpdateIncoming(Vector3 projectile, Vector3 listener)
        {
            if (_far == null) return;
            var q = Proximity(Vector3.Distance(projectile, listener));
            var fMod = 2f + 10f * q;
            _modPhase += fMod * Time.deltaTime;
            var pulse = 0.58f + 0.42f * (0.5f + 0.5f * Mathf.Sin(_modPhase * Mathf.PI * 2f));

            _far.volume = (0.20f + 0.42f * q) * pulse;
            _far.pitch = 0.96f + 0.08f * q;
            if (_near != null)
            {
                _near.volume = (0.04f + 0.58f * q) * pulse;
                _near.pitch = 0.98f + 0.10f * q;
            }
            if (_lpf != null)
                _lpf.cutoffFrequency = Mathf.Lerp(850f, 7200f, q);
        }

        public void StopIncoming()
        {
            if (_far != null) _far.Stop();
            if (_near != null) _near.Stop();
            _far = null;
            _near = null;
            _lpf = null;
            _modPhase = 0f;
        }

        static float Proximity(float distance)
        {
            return 1f - Mathf.Clamp01((distance - DistanceMin) / (DistanceMax - DistanceMin));
        }

        static GameObject Child(Transform parent, string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = Vector3.zero;
            return go;
        }
    }
}
