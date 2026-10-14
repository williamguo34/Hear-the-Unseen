using UnityEngine;

namespace HearTheUnseen
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

        bool HeadLive => Head != null && Head.IsValid;

        void Update()
        {
            if (Hurtbox != null && Head != null) Hurtbox.Follow(Head.transform);
            if (Running && !HeadLive && _live != null && _live.ReachedTarget)
            {
                StopRound();
                return;
            }
            if (!Running || !HeadLive) return;

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
            _live = Spawner.Spawn(Head.transform, WorldRoot, LaserSound, ProjectileTemplate, Saber);
            if (_live == null) return;
            Phase = RoundPhase.Incoming;
        }

        public void StopRound()
        {
            Running = false;
            _live?.StopIncoming();
            ClearLive();
            Phase = RoundPhase.Ready;
            LastResult = RoundResult.None;
            Blocks = 0;
            Hits = 0;
            Dodges = 0;
            _resumeAt = 0f;
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
                point = Saber.ClosestPoint(_live.transform.position);
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
