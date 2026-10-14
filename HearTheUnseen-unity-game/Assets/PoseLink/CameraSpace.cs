using UnityEngine;

namespace HearTheUnseen
{
    /// <summary>
    /// Mac camera metres (Y down) → Unity / Steam Audio (Y up). M = diag(1,-1,1).
    /// Do not convert quaternions across this reflection.
    /// </summary>
    public static class CameraSpace
    {
        public static Vector3 Point(Vector3 camera)
        {
            return new Vector3(camera.x, -camera.y, camera.z);
        }

        public static Vector3 Vec(CamVec camera)
        {
            return Point(new Vector3(camera.x, camera.y, camera.z));
        }

        public static bool Look(Transform target, Vector3 axis, Vector3 up)
        {
            if (axis.sqrMagnitude < 1e-6f) return false;
            if (Mathf.Abs(Vector3.Dot(axis, up)) > 0.98f)
                up = Vector3.up;
            target.rotation = Quaternion.LookRotation(axis, up);
            return true;
        }
    }

    [System.Serializable]
    public struct CamVec
    {
        public float x;
        public float y;
        public float z;

        public Vector3 Camera => new Vector3(x, y, z);
        public bool HasLength => Camera.sqrMagnitude > 1e-8f;
    }
}
