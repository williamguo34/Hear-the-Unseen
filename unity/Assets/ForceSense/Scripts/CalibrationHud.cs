using UnityEngine;

namespace ForceSense
{
    public sealed class CalibrationHud : MonoBehaviour
    {
        public TrackingReceiver Tracking;
        public GameDirector Game;
        public TrackedHeadController Head;
        public TrackedSaberController Saber;

        SciFiHud _view;

        void Awake()
        {
            _view = SciFiHud.Create(transform, () => Tracking?.CalibrateForward(), () => Tracking?.CalibrateSaber(), ToggleRound);
        }

        void Update()
        {
            if (Input.GetKeyDown(KeyCode.C)) Tracking?.CalibrateForward();
            if (Input.GetKeyDown(KeyCode.S)) Tracking?.CalibrateSaber();
            if (Input.GetKeyDown(KeyCode.Space)) ToggleRound();

            var pose = Tracking != null ? Tracking.Pose : null;
            var cal = pose?.Calibration;
            _view?.Refresh(
                Tracking != null ? Tracking.Status : "no tracking",
                Head != null && Head.IsValid,
                Saber != null && Saber.CollisionReady,
                cal != null && cal.forwardSet,
                cal != null && cal.saberReferenceSet,
                Game != null ? Game.Phase : RoundPhase.Ready,
                Game != null ? Game.LastResult : RoundResult.None,
                Game != null ? Game.Blocks : 0,
                Game != null ? Game.Hits : 0,
                Game != null ? Game.Dodges : 0,
                Game != null && Game.Running);
        }

        void ToggleRound()
        {
            if (Game == null) return;
            Game.Running = !Game.Running;
            if (Game.Running) Game.BeginAttack();
        }
    }
}
