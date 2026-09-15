using UnityEngine;

namespace ForceSense
{
    public static class ForceSenseBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void EnsureWorld()
        {
            if (Object.FindObjectOfType<GameDirector>() != null) return;
            Build();
        }

        public static GameDirector Build()
        {
            var world = new GameObject("ForceSenseWorld");
            TrainingChamber.Build(world.transform);

            var tracking = world.AddComponent<TrackingReceiver>();
            var spawner = world.AddComponent<ProjectileSpawner>();
            var judge = world.AddComponent<CollisionJudge>();
            var feedback = world.AddComponent<FeedbackPlayer>();
            var laser = world.AddComponent<LaserSoundDriver>();
            var director = world.AddComponent<GameDirector>();
            var hud = world.AddComponent<CalibrationHud>();
            var debug = world.AddComponent<DebugWorldDraw>();
            var vfx = world.AddComponent<CombatVfx>();
            feedback.Vfx = vfx;

            var headGo = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            headGo.name = "Head";
            headGo.transform.SetParent(world.transform, false);
            headGo.transform.localScale = Vector3.one * 0.16f;
            Object.Destroy(headGo.GetComponent<Collider>());
            SaberVisual.DressHead(headGo);
            var head = headGo.AddComponent<TrackedHeadController>();
            StripAllAudioListeners();
            SpatialAudio.ConfigureListener(headGo);

            var saberGo = new GameObject("Saber");
            saberGo.transform.SetParent(world.transform, false);
            SaberVisual.Build(saberGo);
            var saber = saberGo.AddComponent<TrackedSaberController>();
            var saberSound = saberGo.AddComponent<SaberSoundDriver>();
            saberSound.Saber = saber;

            var hurtGo = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            hurtGo.name = "PlayerHurtbox";
            hurtGo.transform.SetParent(world.transform, false);
            Object.Destroy(hurtGo.GetComponent<Collider>());
            SaberVisual.HideHurtbox(hurtGo);
            var hurt = hurtGo.AddComponent<PlayerHurtbox>();

            var orb = TrainingOrbVisual.Build(world.transform);
            var projectileTemplate = ProjectileVisual.CreateTemplate();
            projectileTemplate.transform.SetParent(world.transform, false);

            director.Head = head;
            director.Saber = saber;
            director.Hurtbox = hurt;
            director.WorldRoot = world.transform;
            director.Spawner = spawner;
            director.Judge = judge;
            director.Feedback = feedback;
            director.LaserSound = laser;
            director.Orb = orb;
            director.ProjectileTemplate = projectileTemplate;
            hud.Tracking = tracking;
            hud.Game = director;
            hud.Head = head;
            hud.Saber = saber;
            debug.Head = head;
            debug.Saber = saber;
            debug.Hurtbox = hurt;

            var bank = AudioBank.Load();
            saberSound.Bind(bank);
            director.BindAudio(bank);

            var poseDriver = world.AddComponent<PoseApplicator>();
            poseDriver.Tracking = tracking;
            poseDriver.Head = head;
            poseDriver.Saber = saber;

            PlaceSpectatorCamera(head);
            return director;
        }

        static void PlaceSpectatorCamera(TrackedHeadController head)
        {
            var camera = Camera.main;
            if (camera == null)
            {
                var go = new GameObject("SpectatorCamera");
                camera = go.AddComponent<Camera>();
                go.tag = "MainCamera";
            }
            var listener = camera.GetComponent<AudioListener>();
            if (listener != null) Object.DestroyImmediate(listener);
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = VisualTheme.Void;
            camera.allowHDR = true;
            camera.allowMSAA = true;
            camera.nearClipPlane = 0.04f;
            camera.farClipPlane = 40f;
            camera.fieldOfView = 75f;
            camera.transform.position = new Vector3(0.4f, 0.85f, 3.35f);
            camera.transform.LookAt(new Vector3(0f, 0.2f, 1.4f));

            var follow = camera.GetComponent<SpectatorFollow>();
            if (follow == null) follow = camera.gameObject.AddComponent<SpectatorFollow>();
            follow.Head = head;
        }

        static void StripAllAudioListeners()
        {
            var listeners = Object.FindObjectsOfType<AudioListener>();
            for (var i = 0; i < listeners.Length; i++)
                Object.DestroyImmediate(listeners[i]);
        }
    }

    public sealed class PoseApplicator : MonoBehaviour
    {
        public TrackingReceiver Tracking;
        public TrackedHeadController Head;
        public TrackedSaberController Saber;

        void Update()
        {
            if (Tracking == null) return;
            var pose = Tracking.Pose;
            if (!pose.Received) return;
            Head?.Apply(pose.Head);
            Saber?.Apply(pose.Saber, pose.Calibration);
        }
    }
}
