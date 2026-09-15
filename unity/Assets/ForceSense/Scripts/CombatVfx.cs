using UnityEngine;

namespace ForceSense
{
    public sealed class CombatVfx : MonoBehaviour
    {
        public void Block(Vector3 point)
        {
            Burst(point, VisualTheme.Blade, "Art/Vfx/spark_05", 36, 3.4f, 0.14f);
            Burst(point, Color.white, "Art/Vfx/flare_01", 1, 0.05f, 0.55f);
            Flash(point, VisualTheme.Blade, 2.4f);
        }

        public void Hit(Vector3 point)
        {
            Burst(point, VisualTheme.Bolt, "Art/Vfx/muzzle_01", 18, 1.6f, 0.22f);
            Burst(point, new Color(1f, 0.35f, 0.15f), "Art/Vfx/star_01", 10, 1.1f, 0.18f);
            Flash(point, VisualTheme.Bolt, 1.8f);
        }

        public void Dodge(Vector3 point)
        {
            Burst(point, VisualTheme.Sensor, "Art/Vfx/circle_05", 8, 0.4f, 0.42f);
            Burst(point, VisualTheme.Sensor, "Art/Vfx/magic_05", 12, 0.8f, 0.2f);
        }

        void Burst(Vector3 point, Color color, string sprite, int count, float speed, float size)
        {
            var go = new GameObject("VfxBurst");
            go.transform.position = point;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.duration = 0.35f;
            main.loop = false;
            main.playOnAwake = true;
            main.startLifetime = 0.35f;
            main.startSpeed = speed;
            main.startSize = size;
            main.startColor = color;
            main.maxParticles = count;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.gravityModifier = 0.15f;

            var emission = ps.emission;
            emission.rateOverTime = 0f;
            emission.SetBursts(new[] { new ParticleSystem.Burst(0f, (short)count) });

            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = 0.03f;

            var colorOver = ps.colorOverLifetime;
            colorOver.enabled = true;
            var gradient = new Gradient();
            gradient.SetKeys(
                new[] { new GradientColorKey(color, 0f), new GradientColorKey(color, 1f) },
                new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0f, 1f) });
            colorOver.color = gradient;

            var sizeOver = ps.sizeOverLifetime;
            sizeOver.enabled = true;
            sizeOver.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0f, 1f, 1f, 0.15f));

            var renderer = go.GetComponent<ParticleSystemRenderer>();
            renderer.renderMode = ParticleSystemRenderMode.Billboard;
            renderer.material = VisualTheme.Additive(color, VisualTheme.Tex(sprite));
            ps.Play();
            Destroy(go, 1.1f);
        }

        void Flash(Vector3 point, Color color, float intensity)
        {
            var go = new GameObject("VfxFlash");
            go.transform.position = point;
            var light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.intensity = intensity;
            light.range = 2.8f;
            Destroy(go, 0.12f);
        }
    }
}
