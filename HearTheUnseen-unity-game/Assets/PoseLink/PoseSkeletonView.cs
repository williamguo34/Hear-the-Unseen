using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace HearTheUnseen
{
    /// <summary>
    /// Display-only upper body. Raw pose points are smoothed here and are not
    /// written back into tracking.
    /// </summary>
    public sealed class PoseSkeletonView : MonoBehaviour
    {
        const int Nose = 0;
        const int LeftShoulder = 11;
        const int RightShoulder = 12;
        const int LeftElbow = 13;
        const int RightElbow = 14;
        const int LeftWrist = 15;
        const int RightWrist = 16;
        const int LeftHip = 23;
        const int RightHip = 24;

        const float SmoothSharpness = 20f;
        const float SnapDistanceM = 0.75f;

        struct JointState
        {
            public Vector3 Position;
            public bool Visible;
            public bool Ready;
        }

        sealed class Limb
        {
            public Transform Transform;
            public Renderer Renderer;
        }

        readonly Dictionary<int, JointState> _joints = new Dictionary<int, JointState>();
        readonly List<Limb> _limbs = new List<Limb>();

        Limb _neck;
        Limb _shoulders;
        Limb _torso;
        Limb _hips;
        Limb _upperLeft;
        Limb _foreLeft;
        Limb _upperRight;
        Limb _foreRight;
        Limb _elbowLeft;
        Limb _elbowRight;

        Material _suit;

        void Awake()
        {
            _suit = new Material(Shader.Find("Standard"));
            _suit.color = new Color(0.34f, 0.36f, 0.40f);
            _suit.SetFloat("_Metallic", 0.06f);
            _suit.SetFloat("_Glossiness", 0.32f);
            _suit.EnableKeyword("_EMISSION");
            _suit.SetColor("_EmissionColor", new Color(0.05f, 0.055f, 0.06f));

            _neck = CreatePart("Neck", PrimitiveType.Cylinder);
            _shoulders = CreatePart("Shoulders", PrimitiveType.Cylinder);
            _torso = CreatePart("Torso", PrimitiveType.Cylinder);
            _hips = CreatePart("Hips", PrimitiveType.Cylinder);
            _upperLeft = CreatePart("UpperArmLeft", PrimitiveType.Cylinder);
            _foreLeft = CreatePart("ForearmLeft", PrimitiveType.Cylinder);
            _upperRight = CreatePart("UpperArmRight", PrimitiveType.Cylinder);
            _foreRight = CreatePart("ForearmRight", PrimitiveType.Cylinder);
            _elbowLeft = CreatePart("ElbowLeft", PrimitiveType.Sphere);
            _elbowRight = CreatePart("ElbowRight", PrimitiveType.Sphere);
        }

        Limb CreatePart(string name, PrimitiveType type)
        {
            var go = GameObject.CreatePrimitive(type);
            go.name = name;
            go.transform.SetParent(transform, false);
            var collider = go.GetComponent<Collider>();
            if (collider != null)
            {
                if (Application.isPlaying) Destroy(collider);
                else DestroyImmediate(collider);
            }
            go.GetComponent<MeshRenderer>().sharedMaterial = _suit;
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.enabled = false;
            var limb = new Limb { Transform = go.transform, Renderer = renderer };
            _limbs.Add(limb);
            return limb;
        }

        public void Apply(SkeletonPose skeleton)
        {
            if (skeleton == null || !skeleton.valid || skeleton.points == null || skeleton.points.Length == 0)
            {
                Hide();
                return;
            }

            var seen = new HashSet<int>();
            for (var i = 0; i < skeleton.points.Length; i++)
            {
                var point = skeleton.points[i];
                seen.Add(point.i);
                Smooth(point.i, CameraSpace.Point(new Vector3(point.x, point.y, point.z)), point.v != 0);
            }

            foreach (var index in new List<int>(_joints.Keys))
            {
                if (seen.Contains(index)) continue;
                var state = _joints[index];
                state.Visible = false;
                _joints[index] = state;
            }

            PoseBody();
        }

        void Smooth(int index, Vector3 target, bool visible)
        {
            _joints.TryGetValue(index, out var state);
            if (!visible)
            {
                state.Visible = false;
                _joints[index] = state;
                return;
            }

            if (!state.Ready || (target - state.Position).sqrMagnitude > SnapDistanceM * SnapDistanceM)
                state.Position = target;
            else
            {
                var blend = 1f - Mathf.Exp(-SmoothSharpness * Time.deltaTime);
                state.Position = Vector3.Lerp(state.Position, target, blend);
            }

            state.Visible = true;
            state.Ready = true;
            _joints[index] = state;
        }

        void PoseBody()
        {
            var leftShoulder = Vector3.zero;
            var rightShoulder = Vector3.zero;
            var leftHip = Vector3.zero;
            var rightHip = Vector3.zero;
            var hasShoulders = TryGet(LeftShoulder, out leftShoulder) && TryGet(RightShoulder, out rightShoulder);
            var hasHips = TryGet(LeftHip, out leftHip) && TryGet(RightHip, out rightHip);
            var shoulderMid = hasShoulders ? (leftShoulder + rightShoulder) * 0.5f : Vector3.zero;
            var hipMid = hasHips ? (leftHip + rightHip) * 0.5f : Vector3.zero;
            var shoulderWidth = hasShoulders ? Vector3.Distance(leftShoulder, rightShoulder) : 0.35f;
            var torsoRadius = Mathf.Clamp(shoulderWidth * 0.46f, 0.09f, 0.16f);
            var armRadius = Mathf.Clamp(shoulderWidth * 0.16f, 0.028f, 0.046f);

            if (hasShoulders)
            {
                PlaceCylinder(_shoulders, leftShoulder, rightShoulder, torsoRadius * 0.55f);
                if (TryGet(Nose, out var nose))
                {
                    var neckTop = Vector3.Lerp(shoulderMid, nose, 0.58f);
                    PlaceCylinder(_neck, shoulderMid, neckTop, armRadius * 0.85f);
                }
                else
                    _neck.Renderer.enabled = false;
            }
            else
            {
                _shoulders.Renderer.enabled = false;
                _neck.Renderer.enabled = false;
            }

            if (hasShoulders && hasHips)
            {
                var chest = Vector3.Lerp(shoulderMid, hipMid, 0.12f);
                var waist = Vector3.Lerp(shoulderMid, hipMid, 0.92f);
                PlaceCylinder(_torso, chest, waist, torsoRadius);
            }
            else
                _torso.Renderer.enabled = false;

            if (hasHips)
                PlaceCylinder(_hips, leftHip, rightHip, torsoRadius * 0.62f);
            else
                _hips.Renderer.enabled = false;

            PlaceArm(_upperLeft, _foreLeft, _elbowLeft, LeftShoulder, LeftElbow, LeftWrist, armRadius);
            PlaceArm(_upperRight, _foreRight, _elbowRight, RightShoulder, RightElbow, RightWrist, armRadius);
        }

        void PlaceArm(Limb upper, Limb fore, Limb elbow, int shoulder, int elbowIndex, int wrist, float radius)
        {
            var hasShoulder = TryGet(shoulder, out var shoulderPos);
            var hasElbow = TryGet(elbowIndex, out var elbowPos);
            var hasWrist = TryGet(wrist, out var wristPos);
            if (hasShoulder && hasElbow)
                PlaceCylinder(upper, shoulderPos, elbowPos, radius);
            else
                upper.Renderer.enabled = false;

            if (hasElbow && hasWrist)
                PlaceCylinder(fore, elbowPos, wristPos, radius * 0.78f);
            else
                fore.Renderer.enabled = false;

            if (hasElbow)
            {
                elbow.Renderer.enabled = true;
                elbow.Transform.position = elbowPos;
                elbow.Transform.localScale = Vector3.one * radius * 2.1f;
            }
            else
                elbow.Renderer.enabled = false;
        }

        bool TryGet(int index, out Vector3 position)
        {
            if (_joints.TryGetValue(index, out var state) && state.Visible && state.Ready)
            {
                position = state.Position;
                return true;
            }

            position = Vector3.zero;
            return false;
        }

        static void PlaceCylinder(Limb limb, Vector3 a, Vector3 b, float radius)
        {
            var delta = b - a;
            var length = delta.magnitude;
            if (length < 0.02f)
            {
                limb.Renderer.enabled = false;
                return;
            }

            limb.Renderer.enabled = true;
            limb.Transform.position = (a + b) * 0.5f;
            limb.Transform.rotation = Quaternion.FromToRotation(Vector3.up, delta / length);
            limb.Transform.localScale = new Vector3(radius * 2f, length * 0.5f, radius * 2f);
        }

        void Hide()
        {
            for (var i = 0; i < _limbs.Count; i++)
                _limbs[i].Renderer.enabled = false;
            var indexes = new List<int>(_joints.Keys);
            for (var i = 0; i < indexes.Count; i++)
            {
                var state = _joints[indexes[i]];
                state.Visible = false;
                _joints[indexes[i]] = state;
            }
        }
    }
}
