# List video capture devices in Media Foundation order.
# OpenCV CAP_MSMF uses the same MFEnumDeviceSources order for camera indices.
param(
    [Parameter(Mandatory = $true)]
    [string]$OutFile
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class WindowsCameras {
    static readonly Guid SourceType = new Guid("c60ac5fe-252a-478f-a0ef-bc8fa5f7cad3");
    static readonly Guid Vidcap = new Guid("8ac3587a-4ae7-42d8-99e0-0a6013eef90f");
    static readonly Guid FriendlyName = new Guid("60d0e559-52f8-4fa2-bbce-acdb34a8ec01");

    const uint COINIT_APARTMENTTHREADED = 2;
    const int RPC_E_CHANGED_MODE = unchecked((int)0x80010106);
    const uint MF_VERSION = 0x00020070;

    [DllImport("ole32.dll")]
    static extern int CoInitializeEx(IntPtr reserved, uint coinit);

    [DllImport("ole32.dll")]
    static extern void CoTaskMemFree(IntPtr ptr);

    [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = true)]
    static extern int MFStartup(uint version, uint flags);

    [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = true)]
    static extern int MFShutdown();

    [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = true)]
    static extern int MFCreateAttributes(out IntPtr attributes, uint initialSize);

    [DllImport("mf.dll", ExactSpelling = true, PreserveSig = true)]
    static extern int MFEnumDeviceSources(IntPtr attributes, out IntPtr activates, out uint count);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate int SetGuidDelegate(IntPtr self, ref Guid key, ref Guid value);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate int GetAllocatedStringDelegate(IntPtr self, ref Guid key, out IntPtr value, out uint length);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate uint ReleaseDelegate(IntPtr self);

    static T Fn<T>(IntPtr com, int slot) where T : class {
        IntPtr vtable = Marshal.ReadIntPtr(com);
        IntPtr method = Marshal.ReadIntPtr(vtable, slot * IntPtr.Size);
        return Marshal.GetDelegateForFunctionPointer(method, typeof(T)) as T;
    }

    static void Check(int hr, string call) {
        if (hr < 0) {
            throw new InvalidOperationException(call + " failed: 0x" + hr.ToString("X8"));
        }
    }

    public static string[] List() {
        int hr = CoInitializeEx(IntPtr.Zero, COINIT_APARTMENTTHREADED);
        if (hr < 0 && hr != RPC_E_CHANGED_MODE) {
            Check(hr, "CoInitializeEx");
        }
        Check(MFStartup(MF_VERSION, 0), "MFStartup");
        IntPtr attributes = IntPtr.Zero;
        try {
            Check(MFCreateAttributes(out attributes, 1), "MFCreateAttributes");
            var setGuid = Fn<SetGuidDelegate>(attributes, 24);
            Guid sourceType = SourceType;
            Guid vidcap = Vidcap;
            Check(setGuid(attributes, ref sourceType, ref vidcap), "SetGUID");
            IntPtr activates;
            uint count;
            Check(MFEnumDeviceSources(attributes, out activates, out count), "MFEnumDeviceSources");
            var names = new List<string>();
            try {
                for (uint i = 0; i < count; i++) {
                    IntPtr activate = Marshal.ReadIntPtr(activates, (int)(i * (uint)IntPtr.Size));
                    if (activate == IntPtr.Zero) {
                        names.Add("");
                        continue;
                    }
                    string name = "";
                    try {
                        var getName = Fn<GetAllocatedStringDelegate>(activate, 13);
                        Guid friendly = FriendlyName;
                        IntPtr wide;
                        uint length;
                        if (getName(activate, ref friendly, out wide, out length) >= 0 && wide != IntPtr.Zero) {
                            name = Marshal.PtrToStringUni(wide) ?? "";
                            CoTaskMemFree(wide);
                        }
                    } finally {
                        Fn<ReleaseDelegate>(activate, 2)(activate);
                    }
                    names.Add(name.Trim());
                }
            } finally {
                if (activates != IntPtr.Zero) {
                    CoTaskMemFree(activates);
                }
            }
            return names.ToArray();
        } finally {
            if (attributes != IntPtr.Zero) {
                Fn<ReleaseDelegate>(attributes, 2)(attributes);
            }
            MFShutdown();
        }
    }
}
'@ -Language CSharp

$names = [WindowsCameras]::List()
$lines = New-Object System.Collections.Generic.List[string]
for ($i = 0; $i -lt $names.Length; $i++) {
    if ([string]::IsNullOrWhiteSpace($names[$i])) { continue }
    $lines.Add("$i`t$($names[$i])")
}
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($OutFile, $lines.ToArray(), $utf8)
