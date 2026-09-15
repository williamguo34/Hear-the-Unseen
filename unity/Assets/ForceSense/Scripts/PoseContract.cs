using UnityEngine;

namespace ForceSense
{
    [System.Serializable]
    public class HeadPose
    {
        public CamVec positionCamM;
        public CamVec forwardCam;
        public CamVec upCam;
        public float yawRad;
        public bool valid;
        public float quality;
    }

    [System.Serializable]
    public class SaberPose
    {
        public CamVec handlePositionCamM;
        public CamVec bladeAxisCam;
        public CamVec bladeUpCam;
        public float angularSpeedRadS;
        public string positionSource;
        public CamVec relativeToHeadM;
        public bool valid;
        public string wrist;
    }

    [System.Serializable]
    public class CalibrationState
    {
        public bool forwardSet;
        public bool saberReferenceSet;
    }

    [System.Serializable]
    public class PoseMetrics
    {
        public float fps;
        public float detectMs;
        public int droppedCaptureFrames;
    }

    [System.Serializable]
    public class UnityPoseMessage
    {
        public string type;
        public float timestampMs;
        public HeadPose head;
        public SaberPose saber;
        public CalibrationState calibration;
        public PoseMetrics metrics;
    }

    public sealed class LivePose
    {
        public float TimestampMs;
        public HeadPose Head = new HeadPose();
        public SaberPose Saber = new SaberPose();
        public CalibrationState Calibration = new CalibrationState();
        public PoseMetrics Metrics = new PoseMetrics();
        public bool Received;

        public void CopyFrom(UnityPoseMessage message)
        {
            TimestampMs = message.timestampMs;
            Head = message.head ?? Head;
            Saber = message.saber ?? Saber;
            Calibration = message.calibration ?? Calibration;
            Metrics = message.metrics ?? Metrics;
            Received = true;
        }
    }
}
