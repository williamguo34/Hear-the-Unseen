using UnityEngine;

namespace ForceSense
{
    public enum RoundPhase
    {
        Ready,
        Incoming,
        Feedback
    }

    public sealed class GameDirector : MonoBehaviour
    {
        public TrackedHeadController Head;
        public TrackedSaberController Saber;
        public PlayerHurtbox Hurtbox;
        public Transform WorldRoot;
        public ProjectileSpawner Spawner;
        public CollisionJudge Judge;
        public FeedbackPlayer Feedback;
        public LaserSoundDriver LaserSound;
        public TrainingOrbVisual Orb;
        public GameObject ProjectileTemplate;

        [SerializeField] float gapAfterResult = 0.85f;
        [SerializeField] bool autoPlay = true;

        public RoundPhase Phase { get; private set; } = RoundPhase.Ready;
        public RoundResult LastResult { get; private set; }
        public int Blocks { get; private set; }
        public int Hits { get; private set; }
        public int Dodges { get; private set; }
        public bool Running { get; set; }

        Projectile _live;
        float _resumeAt;

        public void BindAudio(AudioBank bank)
        {
            LaserSound.Bind(bank);
            Feedback.Bind(bank);
        }

        void Update()
        {
            if (Hurtbox != null && Head != null) Hurtbox.Follow(Head.transform);
            if (!Running || Head == null || !Head.IsValid) return;

            if (Phase == RoundPhase.Ready && autoPlay && Time.time >= _resumeAt)
                BeginAttack();
            else if (Phase == RoundPhase.Incoming)
                TickIncoming();
            else if (Phase == RoundPhase.Feedback && Time.time >= _resumeAt)
                Phase = RoundPhase.Ready;
        }

        public void BeginAttack()
        {
            if (!Head.IsValid) return;
            ClearLive();
            _live = Spawner.Spawn(Head.transform, WorldRoot, LaserSound, ProjectileTemplate);
            if (_live != null) Orb?.CueShot(_live.Origin);
            Phase = RoundPhase.Incoming;
        }

        void TickIncoming()
        {
            var result = Judge.Evaluate(_live, Saber, Hurtbox);
            if (result == RoundResult.None) return;
            Finish(result);
        }

        void Finish(RoundResult result)
        {
            LastResult = result;
            var point = _live != null ? _live.transform.position : Head.transform.position;
            if (result == RoundResult.Block && _live != null && Saber != null)
                point = Judge.ClashPoint(_live, Saber);
            _live?.StopIncoming();
            switch (result)
            {
                case RoundResult.Block:
                    Blocks++;
                    Feedback.Block(point);
                    break;
                case RoundResult.Hit:
                    Hits++;
                    Feedback.Hit(point);
                    break;
                case RoundResult.Dodge:
                    Dodges++;
                    Feedback.Dodge(_live != null ? _live.Target : point);
                    break;
            }
            ClearLive();
            Phase = RoundPhase.Feedback;
            _resumeAt = Time.time + gapAfterResult;
        }

        void ClearLive()
        {
            if (_live != null) Destroy(_live.gameObject);
            _live = null;
        }
    }
}
