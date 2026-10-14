using UnityEngine;

namespace HearTheUnseen
{
    public sealed class AudioBank
    {
        public AudioClip SaberHum;
        public AudioClip SwingLow;
        public AudioClip SwingMid;
        public AudioClip SwingFast;
        public AudioClip[] Launch;
        public AudioClip Incoming;
        public AudioClip IncomingNear;
        public AudioClip[] BlockAttack;
        public AudioClip BlockElectric;
        public AudioClip SparkTail;
        public AudioClip[] HitImpact;
        public AudioClip[] Dodge;

        public static AudioBank Load()
        {
            return new AudioBank
            {
                SaberHum = Clip("Audio/Saber/saber_hum_loop"),
                SwingLow = Clip("Audio/Saber/swing_low_loop"),
                SwingMid = Clip("Audio/Saber/swing_mid_loop"),
                SwingFast = Clip("Audio/Saber/swing_fast_loop"),
                Launch = new[]
                {
                    Clip("Audio/Projectile/laser_launch_01"),
                    Clip("Audio/Projectile/laser_launch_02")
                },
                Incoming = Clip("Audio/Projectile/incoming_loop"),
                IncomingNear = Clip("Audio/Projectile/incoming_near_loop"),
                BlockAttack = new[]
                {
                    Clip("Audio/Block/block_attack_01"),
                    Clip("Audio/Block/block_attack_02"),
                    Clip("Audio/Block/block_attack_03")
                },
                BlockElectric = Clip("Audio/Block/block_electric"),
                SparkTail = Clip("Audio/Block/spark_tail"),
                HitImpact = new[]
                {
                    Clip("Audio/Hit/hit_impact_01"),
                    Clip("Audio/Hit/hit_impact_02"),
                    Clip("Audio/Hit/hit_impact_03")
                },
                Dodge = new[]
                {
                    Clip("Audio/Dodge/passby_01"),
                    Clip("Audio/Dodge/passby_02")
                }
            };
        }

        public AudioClip Pick(AudioClip[] clips)
        {
            if (clips == null || clips.Length == 0) return null;
            return clips[Random.Range(0, clips.Length)];
        }

        static AudioClip Clip(string path)
        {
            return Resources.Load<AudioClip>(path);
        }
    }
}
