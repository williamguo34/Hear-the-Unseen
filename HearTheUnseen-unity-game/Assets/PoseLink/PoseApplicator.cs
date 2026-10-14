using UnityEngine;

namespace HearTheUnseen
{
    public sealed class PoseApplicator : MonoBehaviour
    {
        public TrackingReceiver Tracking;
        public TrackedHeadController Head;
        public TrackedSaberController Saber;
        public PoseSkeletonView Skeleton;

        void Update()
        {
            if (Tracking == null) return;
            var pose = Tracking.Pose;
            if (!pose.Received) return;
            Head?.Apply(pose.Head);
            Saber?.Apply(pose.Saber);
            Skeleton?.Apply(pose.Skeleton);
        }
    }
}
