using UnityEngine;

namespace HearTheUnseen
{
    public sealed class Projectile : MonoBehaviour
    {
        public Vector3 Origin { get; private set; }
        public Vector3 Target { get; private set; }
        public float FlightSeconds { get; private set; }
        public float Age { get; private set; }
        public bool Flying { get; private set; }

        LaserSoundDriver _sound;
        ProjectileAudio _audio;
        Transform _listener;

        public void Launch(Vector3 origin, Vector3 target, float flightSeconds, LaserSoundDriver sound, Transform listener)
        {
            Origin = origin;
            Target = target;
            FlightSeconds = Mathf.Max(0.15f, flightSeconds);
            Age = 0f;
            Flying = true;
            transform.SetParent(null, true);
            transform.position = origin;
            _listener = listener;
            _sound = sound;
            _audio = GetComponent<ProjectileAudio>();
            _sound?.PlayLaunch(origin);
            _audio?.Begin();
        }

        void Update()
        {
            if (!Flying) return;
            Age += Time.deltaTime;
            var t = Mathf.Clamp01(Age / FlightSeconds);
            transform.position = Vector3.Lerp(Origin, Target, t);
            var ears = _listener != null ? _listener.position : Target;
            _audio?.Tick(transform.position, ears);
        }

        public bool ReachedTarget => Flying && Age >= FlightSeconds;

        public void StopIncoming()
        {
            Flying = false;
            _audio?.End();
        }
    }
}
