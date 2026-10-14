using UnityEngine;

namespace HearTheUnseen
{
    public sealed class LaserSoundDriver : MonoBehaviour
    {
        AudioBank _bank;

        public void Bind(AudioBank bank)
        {
            _bank = bank;
        }

        public void PlayLaunch(Vector3 origin)
        {
            if (_bank == null) return;
            SpatialAudio.PlayOneShotAt(_bank.Pick(_bank.Launch), origin, 0.48f, Random.Range(0.96f, 1.04f));
        }
    }
}
