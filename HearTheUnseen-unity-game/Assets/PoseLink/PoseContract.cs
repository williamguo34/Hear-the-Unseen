using UnityEngine;

namespace HearTheUnseen
{
    [System.Serializable]
    public class HeadPose
    {
        public CamVec positionCamM;
        public CamVec forwardCam;
        public CamVec upCam;
        public bool valid;
        public float quality;
        public string cue;
    }

    [System.Serializable]
    public class SaberPose
    {
        public CamVec handlePositionCamM;
        public CamVec bladeAxisCam;
        public CamVec bladeUpCam;
        public float angularSpeedRadS;
        public string positionSource;
        public bool valid;
    }

    [System.Serializable]
    public class CalibrationState
    {
        public bool forwardSet;
        public bool saberReferenceSet;
        public string saberHand;
    }

    [System.Serializable]
    public class SkeletonJoint
    {
        public int i;
        public float x;
        public float y;
        public float z;
        public int v;
    }

    [System.Serializable]
    public class SkeletonPose
    {
        public bool valid;
        public SkeletonJoint[] points;
    }

    [System.Serializable]
    public class PoseMetrics
    {
        public float fps;
        public float detectMs;
    }

    [System.Serializable]
    public class UnityPoseMessage
    {
        public string type;
        public HeadPose head;
        public SaberPose saber;
        public CalibrationState calibration;
        public SkeletonPose skeleton;
        public PoseMetrics metrics;
    }

    public sealed class LivePose
    {
        public HeadPose Head = new HeadPose();
        public SaberPose Saber = new SaberPose();
        public CalibrationState Calibration = new CalibrationState();
        public SkeletonPose Skeleton = new SkeletonPose();
        public PoseMetrics Metrics = new PoseMetrics();
        public bool Received;

        public void CopyFrom(UnityPoseMessage message)
        {
            Head = message.head ?? Head;
            Saber = message.saber ?? Saber;
            Calibration = message.calibration ?? Calibration;
            Skeleton = message.skeleton ?? Skeleton;
            Metrics = message.metrics ?? Metrics;
            Received = true;
        }
    }
}
