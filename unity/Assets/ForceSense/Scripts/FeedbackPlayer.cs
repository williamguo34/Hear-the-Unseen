using UnityEngine;

namespace ForceSense
{
    public sealed class FeedbackPlayer : MonoBehaviour
    {
        public CombatVfx Vfx;

        AudioBank _bank;

        public void Bind(AudioBank bank)
        {
            _bank = bank;
        }

        public void Block(Vector3 clashPoint)
        {
            TrackingReceiver.Instance?.Vibrate();
            PlayLayers(clashPoint,
                (_bank != null ? _bank.Pick(_bank.BlockAttack) : null, 1f),
                (_bank != null ? _bank.BlockElectric : null, 0.78f),
                (_bank != null ? _bank.SparkTail : null, 0.28f));
            Vfx?.Block(clashPoint);
        }

        public void Hit(Vector3 point)
        {
            PlayLayers(point,
                (_bank != null ? _bank.Pick(_bank.HitZap) : null, 0.72f),
                (_bank != null ? _bank.HitBody : null, 0.95f));
            Vfx?.Hit(point);
        }

        public void Dodge(Vector3 point)
        {
            PlayLayers(point,
                (_bank != null ? _bank.Pick(_bank.Dodge) : null, 0.68f));
            Vfx?.Dodge(point);
        }

        void PlayLayers(Vector3 position, params (AudioClip clip, float volume)[] layers)
        {
            var pitch = Random.Range(0.96f, 1.04f);
            var gain = DbToLin(Random.Range(-1f, 1f));
            for (var i = 0; i < layers.Length; i++)
            {
                var layer = layers[i];
                SpatialAudio.PlayOneShotAt(layer.clip, position, layer.volume * gain, pitch);
            }
        }

        static float DbToLin(float db)
        {
            return Mathf.Pow(10f, db / 20f);
        }
    }
}
