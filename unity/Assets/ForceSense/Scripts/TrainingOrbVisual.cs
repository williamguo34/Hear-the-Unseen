using UnityEngine;

namespace ForceSense
{
    public sealed class TrainingOrbVisual : MonoBehaviour
    {
        Transform _eye;
        Transform _emitter;
        Light _glow;
        Vector3 _home;
        Vector3 _look = Vector3.forward;
        float _pulse;

        public static TrainingOrbVisual Build(Transform parent)
        {
            var root = new GameObject("TrainingOrb");
            root.transform.SetParent(parent, false);
            root.transform.position = new Vector3(0f, 0.42f, 2.85f);

            var body = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            body.name = "Shell";
            body.transform.SetParent(root.transform, false);
            body.transform.localScale = Vector3.one * 0.34f;
            Object.Destroy(body.GetComponent<Collider>());
            body.GetComponent<MeshRenderer>().sharedMaterial = VisualTheme.OrbShell();

            Band(root.transform, "Equator", 0.176f, 0.012f, 0.176f, Quaternion.identity);
            Band(root.transform, "Meridian", 0.176f, 0.012f, 0.176f, Quaternion.Euler(90f, 0f, 0f));
            Band(root.transform, "Belt", 0.182f, 0.006f, 0.12f, Quaternion.identity);

            var eye = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            eye.name = "Sensor";
            eye.transform.SetParent(root.transform, false);
            eye.transform.localPosition = new Vector3(0f, 0.04f, 0.155f);
            eye.transform.localScale = Vector3.one * 0.07f;
            Object.Destroy(eye.GetComponent<Collider>());
            eye.GetComponent<MeshRenderer>().sharedMaterial = VisualTheme.Glow(VisualTheme.Sensor, 3.2f);

            var emitter = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            emitter.name = "Emitter";
            emitter.transform.SetParent(root.transform, false);
            emitter.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
            emitter.transform.localPosition = new Vector3(0f, -0.02f, 0.17f);
            emitter.transform.localScale = new Vector3(0.055f, 0.03f, 0.055f);
            Object.Destroy(emitter.GetComponent<Collider>());
            emitter.GetComponent<MeshRenderer>().sharedMaterial = VisualTheme.Glow(VisualTheme.Bolt, 1.4f);

            var vent = GameObject.CreatePrimitive(PrimitiveType.Cube);
            vent.name = "Panel";
            vent.transform.SetParent(root.transform, false);
            vent.transform.localPosition = new Vector3(0f, -0.11f, 0.08f);
            vent.transform.localScale = new Vector3(0.16f, 0.03f, 0.08f);
            Object.Destroy(vent.GetComponent<Collider>());
            vent.GetComponent<MeshRenderer>().sharedMaterial = VisualTheme.Trim();

            var lightGo = new GameObject("OrbLight");
            lightGo.transform.SetParent(root.transform, false);
            var light = lightGo.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = VisualTheme.Sensor;
            light.intensity = 0.85f;
            light.range = 2.4f;

            var visual = root.AddComponent<TrainingOrbVisual>();
            visual._eye = eye.transform;
            visual._emitter = emitter.transform;
            visual._glow = light;
            visual._home = root.transform.position;
            visual._look = TrainingChamber.PadCenter + Vector3.up * 1.15f - root.transform.position;
            return visual;
        }

        static void Band(Transform parent, string name, float x, float y, float z, Quaternion rotation)
        {
            var band = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            band.name = name;
            band.transform.SetParent(parent, false);
            band.transform.localRotation = rotation;
            band.transform.localScale = new Vector3(x * 2f, y, z * 2f);
            Object.Destroy(band.GetComponent<Collider>());
            band.GetComponent<MeshRenderer>().sharedMaterial = VisualTheme.Trim();
        }

        public void CueShot(Vector3 worldOrigin)
        {
            _look = worldOrigin - transform.position;
            if (_look.sqrMagnitude < 1e-4f) _look = Vector3.forward;
            _pulse = 1f;
        }

        void Update()
        {
            var hover = Mathf.Sin(Time.time * 1.15f) * 0.045f;
            transform.position = _home + Vector3.up * hover;
            if (_look.sqrMagnitude > 1e-6f)
            {
                var face = Quaternion.LookRotation(_look.normalized, Vector3.up);
                transform.rotation = Quaternion.Slerp(transform.rotation, face, Time.deltaTime * 3.5f);
            }

            _pulse = Mathf.MoveTowards(_pulse, 0f, Time.deltaTime * 1.6f);
            if (_glow != null)
                _glow.intensity = 0.7f + _pulse * 2.2f;
            if (_emitter != null)
                _emitter.localScale = new Vector3(0.055f + _pulse * 0.03f, 0.03f, 0.055f + _pulse * 0.03f);
            if (_eye != null)
                _eye.localScale = Vector3.one * (0.07f + _pulse * 0.025f);
        }
    }
}
