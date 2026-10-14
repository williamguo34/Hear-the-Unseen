using UnityEngine;

namespace HearTheUnseen
{
    public static class TrainingChamber
    {
        public const float FloorY = -1.12f;
        public const float Height = 3.15f;
        public const float HalfWidth = 3.6f;
        public const float ZNear = -3.0f;
        public const float ZFar = 8.15f;
        public static readonly Vector3 PadCenter = new Vector3(0f, FloorY + 0.02f, 1.55f);
        public static Vector3 GazePoint => PadCenter + Vector3.up * 1.15f;
    }
}
