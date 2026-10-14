using UnityEngine;

namespace HearTheUnseen
{
    public sealed class HeadListenerAnchor : MonoBehaviour
    {
        void OnEnable() => SpatialAudio.BindListener(transform);
        void Start() => SpatialAudio.BindListener(transform);
    }
}
