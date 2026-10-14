using UnityEngine;

namespace HearTheUnseen
{
    public sealed class HearTheUnseenSession : MonoBehaviour
    {
        [SerializeField] SaberSoundDriver saberSound;
        [SerializeField] GameDirector director;
        [SerializeField] GameObject listenerHead;

        bool _up;

        public void Assign(SaberSoundDriver sound, GameDirector game, GameObject head)
        {
            saberSound = sound;
            director = game;
            listenerHead = head;
            if (Application.isPlaying) BringUp();
        }

        void Start() => BringUp();

        void BringUp()
        {
            if (_up) return;
            _up = true;
            VisualTheme.ApplyEnvironment();
            if (listenerHead != null) SpatialAudio.ConfigureListener(listenerHead);
            var bank = AudioBank.Load();
            if (saberSound != null) saberSound.Bind(bank);
            if (director != null) director.BindAudio(bank);
        }
    }
}
