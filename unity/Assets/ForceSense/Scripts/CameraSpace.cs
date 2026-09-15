using UnityEngine;

namespace ForceSense
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

        public static Vector3 Direction(Vector3 camera)
        {
            return Point(camera);
        }

        public static Vector3 Vec(CamVec camera)
        {
            return Point(new Vector3(camera.x, camera.y, camera.z));
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
