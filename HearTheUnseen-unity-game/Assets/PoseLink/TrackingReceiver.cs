using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

namespace HearTheUnseen
{
    [DefaultExecutionOrder(-100)]
    public sealed class TrackingReceiver : MonoBehaviour
    {
        public static TrackingReceiver Instance { get; private set; }

        [SerializeField] int listenPort = 8766;
        [SerializeField] string commandHost = "127.0.0.1";
        [SerializeField] int commandPort = 8767;

        readonly LivePose _pose = new LivePose();
        readonly object _gate = new object();
        byte[] _pending;
        UdpClient _client;
        Thread _thread;
        volatile bool _running;
        UdpClient _command;
        string _status = "waiting for Python UDP 8766";

        public LivePose Pose
        {
            get
            {
                lock (_gate) return _pose;
            }
        }

        public string Status => _status;

        bool _connected;
        float _lastPacketRealtime;

        void Awake()
        {
            Instance = this;
            _command = new UdpClient();
            _client = new UdpClient(listenPort);
            _client.Client.ReceiveTimeout = 250;
            _running = true;
            _thread = new Thread(ReceiveLoop) { IsBackground = true, Name = "HearTheUnseenUDP" };
            _thread.Start();
        }

        void Update()
        {
            byte[] packet = null;
            lock (_gate)
            {
                packet = _pending;
                _pending = null;
            }
            if (packet != null)
            {
                try
                {
                    var json = Encoding.UTF8.GetString(packet);
                    var message = JsonUtility.FromJson<UnityPoseMessage>(json);
                    if (message != null && message.type == "unity_pose")
                    {
                        lock (_gate) _pose.CopyFrom(message);
                        _connected = true;
                        _lastPacketRealtime = Time.realtimeSinceStartup;
                        _status = $"pose {_pose.Metrics.fps:0.0} fps  detect {_pose.Metrics.detectMs:0.0} ms";
                    }
                }
                catch (Exception error)
                {
                    _status = error.Message;
                }
            }
            var age = _connected ? Time.realtimeSinceStartup - _lastPacketRealtime : 999f;
            if (age > 1.5f)
            {
                _connected = false;
                _status = "waiting for Python UDP 8766";
            }
        }

        void ReceiveLoop()
        {
            var any = new IPEndPoint(IPAddress.Any, listenPort);
            while (_running)
            {
                try
                {
                    var data = _client.Receive(ref any);
                    lock (_gate) _pending = data;
                }
                catch (SocketException)
                {
                }
                catch (ObjectDisposedException)
                {
                    break;
                }
            }
        }

        public void SendCommand(string type)
        {
            var payload = Encoding.UTF8.GetBytes("{\"type\":\"" + type + "\"}");
            _command.Send(payload, payload.Length, commandHost, commandPort);
        }

        public void CalibrateForward() => SendCommand("calibrate_forward");
        public void CalibrateSaber() => SendCommand("calibrate_saber_reference");
        public void Vibrate() => SendCommand("vibrate");

        public void SetSaberHand(string hand)
        {
            if (hand != "left" && hand != "right") return;
            var payload = Encoding.UTF8.GetBytes("{\"type\":\"set_saber_hand\",\"hand\":\"" + hand + "\"}");
            _command.Send(payload, payload.Length, commandHost, commandPort);
        }

        void OnDestroy()
        {
            _running = false;
            _client?.Close();
            _command?.Close();
            if (Instance == this) Instance = null;
        }
    }
}
