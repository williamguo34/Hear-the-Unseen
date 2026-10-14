import AVFoundation
import Foundation

// Same enumeration OpenCV 4.11 uses in cap_avfoundation_mac.mm:
// video + muxed devices, then sort by uniqueID.
let video = AVCaptureDevice.devices(for: .video)
let muxed = AVCaptureDevice.devices(for: .muxed)
var seen = Set<String>()
var devices: [AVCaptureDevice] = []
for device in video + muxed {
    if seen.insert(device.uniqueID).inserted {
        devices.append(device)
    }
}
devices.sort { $0.uniqueID < $1.uniqueID }

for (index, device) in devices.enumerated() {
    print("\(index)\t\(device.localizedName)")
}
