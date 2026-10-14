using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace HearTheUnseen
{
    public sealed class SciFiHud : MonoBehaviour
    {
        [SerializeField] Text _tracking;
        [SerializeField] Text _calibration;
        [SerializeField] Text _score;
        [SerializeField] Text _phase;
        [SerializeField] Text _startLabel;
        [SerializeField] Text _audioOnlyLabel;
        [SerializeField] Text _handLabel;
        [SerializeField] Image _audioOnlyImage;
        [SerializeField] Text _faceCue;
        AudioSource _voice;
        string _spokenCue;
        float _speakAgainAt;
        float _cueLockedUntil;
        readonly Dictionary<string, AudioClip> _cueClips = new Dictionary<string, AudioClip>();

        public void SetAudioOnly(bool on)
        {
            if (_audioOnlyLabel != null)
                _audioOnlyLabel.text = on ? "AUDIO ONLY  ON  [V]" : "AUDIO ONLY  [V]";
            if (_audioOnlyImage != null)
                _audioOnlyImage.color = on ? new Color(0.85f, 0.42f, 0.18f, 1f) : Color.white;
        }

        public void SetFaceCue(string cue)
        {
            EnsureFaceCue();
            if (_faceCue == null) return;
            var text = FaceCueText(cue);
            var show = !string.IsNullOrEmpty(text);
            if (!show)
            {
                _faceCue.transform.parent.gameObject.SetActive(false);
                SpeakFaceCue(null);
                return;
            }
            if (CueSentenceBusy)
                return;
            _faceCue.transform.parent.gameObject.SetActive(true);
            _faceCue.text = text;
            SpeakFaceCue(cue);
        }

        public void SetSaberHand(string hand)
        {
            if (_handLabel == null) return;
            var shown = hand == "left" ? "LEFT" : hand == "auto" ? "AUTO" : "RIGHT";
            _handLabel.text = $"SABER HAND  {shown}  [H]";
        }

        public void Refresh(string status, bool headLive, bool saberReady, bool forwardSet, bool saberSet, RoundPhase phase, RoundResult last, int blocks, int hits, int dodges, bool running)
        {
            if (_tracking != null)
                _tracking.text = $"HEAD     {(headLive ? "LIVE" : "---")}\nSABER    {(saberReady ? "READY" : "WAIT")}\nLINK     {ShortStatus(status)}";
            if (_calibration != null)
                _calibration.text = $"FORWARD  {(forwardSet ? "SET" : "NEED")}\nSABER    {(saberSet ? "SET" : "NEED")}";
            if (_score != null)
                _score.text = $"BLOCKS   {blocks:00}\nHITS     {hits:00}\nDODGES   {dodges:00}";
            if (_phase != null)
                _phase.text = running ? $"{phase.ToString().ToUpper()}   LAST {last.ToString().ToUpper()}" : "STANDBY";
            if (_startLabel != null)
                _startLabel.text = running ? "STOP  [SPACE]" : "START TRAINING  [SPACE]";
            ColorStatus(_tracking, headLive && saberReady);
        }

        static string ShortStatus(string status)
        {
            if (string.IsNullOrEmpty(status)) return "OFF";
            return status.Length > 28 ? status.Substring(0, 28) : status;
        }

        static void ColorStatus(Text text, bool ready)
        {
            if (text == null) return;
            text.color = ready ? VisualTheme.UiReady : VisualTheme.UiText;
        }

        void EnsureFaceCue()
        {
            if (_faceCue != null) return;
            var canvas = GetComponentInChildren<Canvas>(true);
            if (canvas == null) return;
            var dim = VisualTheme.Slice(new Color(0.05f, 0.06f, 0.08f, 0.8f), new Color(0.25f, 0.4f, 0.48f));
            var go = new GameObject("FaceCue", typeof(RectTransform), typeof(Image));
            var rect = go.GetComponent<RectTransform>();
            rect.SetParent(canvas.transform, false);
            rect.anchorMin = new Vector2(0.5f, 0.5f);
            rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = Vector2.zero;
            rect.sizeDelta = new Vector2(560f, 56f);
            var image = go.GetComponent<Image>();
            image.sprite = dim;
            image.type = Image.Type.Sliced;
            image.raycastTarget = false;

            _faceCue = Label(go.transform, "", 0, 0, 560, 56, 22, FontStyle.Bold, VisualTheme.UiText);
            var labelRect = _faceCue.GetComponent<RectTransform>();
            labelRect.anchorMin = Vector2.zero;
            labelRect.anchorMax = Vector2.one;
            labelRect.pivot = new Vector2(0.5f, 0.5f);
            labelRect.offsetMin = new Vector2(16, 6);
            labelRect.offsetMax = new Vector2(-16, -6);
            _faceCue.alignment = TextAnchor.MiddleCenter;
            _faceCue.raycastTarget = false;
            go.SetActive(false);
        }

        bool CueSentenceBusy => !string.IsNullOrEmpty(_spokenCue) && Time.unscaledTime < _cueLockedUntil;

        void SpeakFaceCue(string cue)
        {
            if (string.IsNullOrEmpty(cue))
            {
                if (_voice != null && _voice.isPlaying) _voice.Stop();
                _spokenCue = null;
                _cueLockedUntil = 0f;
                return;
            }

            if (CueSentenceBusy)
                return;

            if (cue == _spokenCue && Time.unscaledTime < _speakAgainAt)
                return;

            var clip = FaceCueClip(cue);
            if (clip == null) return;
            EnsureVoice();
            _voice.clip = clip;
            _voice.Play();
            _spokenCue = cue;
            _cueLockedUntil = Time.unscaledTime + clip.length;
            _speakAgainAt = _cueLockedUntil + 2f;
        }

        void EnsureVoice()
        {
            if (_voice != null) return;
            _voice = gameObject.AddComponent<AudioSource>();
            _voice.playOnAwake = false;
            _voice.spatialBlend = 0f;
            _voice.spatialize = false;
            _voice.dopplerLevel = 0f;
            _voice.volume = 0.9f;
            _voice.bypassEffects = true;
            _voice.bypassListenerEffects = true;
            _voice.bypassReverbZones = true;
        }

        AudioClip FaceCueClip(string cue)
        {
            if (_cueClips.TryGetValue(cue, out var cached)) return cached;
            string path;
            switch (cue)
            {
                case "turn-left": path = "Audio/Cue/turn_left"; break;
                case "turn-right": path = "Audio/Cue/turn_right"; break;
                case "turn": path = "Audio/Cue/turn_back"; break;
                case "far": path = "Audio/Cue/step_closer"; break;
                default: path = null; break;
            }
            var clip = path == null ? null : Resources.Load<AudioClip>(path);
            _cueClips[cue] = clip;
            return clip;
        }

        static string FaceCueText(string cue)
        {
            switch (cue)
            {
                case "turn-left": return "TURN LEFT";
                case "turn-right": return "TURN RIGHT";
                case "turn": return "TURN BACK";
                case "far": return "STEP CLOSER";
                default: return "";
            }
        }

        static Text Label(Transform parent, string text, float x, float y, float w, float h, int size, FontStyle style = FontStyle.Normal, Color? color = null)
        {
            var go = new GameObject("Label", typeof(RectTransform), typeof(Text));
            var rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = new Vector2(0, 1);
            rect.anchorMax = new Vector2(0, 1);
            rect.pivot = new Vector2(0, 1);
            rect.anchoredPosition = new Vector2(x, -y);
            rect.sizeDelta = new Vector2(w, h);
            var ui = go.GetComponent<Text>();
            ui.font = VisualTheme.UiFont();
            ui.text = text;
            ui.fontSize = size;
            ui.fontStyle = style;
            ui.color = color ?? VisualTheme.UiText;
            ui.alignment = TextAnchor.UpperLeft;
            ui.horizontalOverflow = HorizontalWrapMode.Overflow;
            ui.verticalOverflow = VerticalWrapMode.Overflow;
            return ui;
        }
    }
}
