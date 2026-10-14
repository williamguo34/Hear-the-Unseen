using UnityEngine;

namespace HearTheUnseen
{
    public sealed class CalibrationHud : MonoBehaviour
    {
        public TrackingReceiver Tracking;
        public GameDirector Game;
        public TrackedHeadController Head;
        public TrackedSaberController Saber;
        public Camera ViewCamera;

        [SerializeField] SciFiHud _view;
        bool _audioOnly;

        [UnityEngine.Scripting.Preserve]
        public void PressForward() => Tracking?.CalibrateForward();

        [UnityEngine.Scripting.Preserve]
        public void PressSaber() => Tracking?.CalibrateSaber();

        [UnityEngine.Scripting.Preserve]
        public void PressHand() => ToggleSaberHand();

        [UnityEngine.Scripting.Preserve]
        public void PressStart() => ToggleRound();

        [UnityEngine.Scripting.Preserve]
        public void PressAudioOnly() => ToggleAudioOnly();

        void Update()
        {
            if (Input.GetKeyDown(KeyCode.C)) Tracking?.CalibrateForward();
            if (Input.GetKeyDown(KeyCode.S)) Tracking?.CalibrateSaber();
            if (Input.GetKeyDown(KeyCode.H)) ToggleSaberHand();
            if (Input.GetKeyDown(KeyCode.V)) ToggleAudioOnly();
            if (Input.GetKeyDown(KeyCode.Space)) ToggleRound();

            var pose = Tracking != null ? Tracking.Pose : null;
            var cal = pose?.Calibration;
            _view?.SetSaberHand(cal != null ? cal.saberHand : "right");
            _view?.SetFaceCue(pose != null && pose.Head != null ? pose.Head.cue : null);
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
            if (Game.Running)
            {
                Game.StopRound();
                return;
            }

            Game.Running = true;
            Game.BeginAttack();
        }

        void ToggleSaberHand()
        {
            var current = Tracking != null ? Tracking.Pose.Calibration.saberHand : null;
            Tracking?.SetSaberHand(current == "left" ? "right" : "left");
        }

        void ToggleAudioOnly()
        {
            _audioOnly = !_audioOnly;
            if (ViewCamera != null) ViewCamera.enabled = !_audioOnly;
            _view?.SetAudioOnly(_audioOnly);
        }
    }
}
