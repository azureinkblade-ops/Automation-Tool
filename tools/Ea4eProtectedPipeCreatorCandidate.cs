// Source-only creator candidate. Do not call Open before bounded native qualification.
using System;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eProtectedPipeCreatorCandidate
{
    private const uint PipeAccessInbound = 0x00000001;
    private const uint FileFlagOverlapped = 0x40000000;
    private const uint FileFlagFirstPipeInstance = 0x00080000;
    private const uint AccessSystemSecurity = 0x01000000;
    private const uint PipeTypeMessage = 0x00000004;
    private const uint PipeReadmodeMessage = 0x00000002;
    private const uint PipeRejectRemoteClients = 0x00000008;
    private const uint FrameLimit = 512;

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes
    {
        internal int Length;
        internal IntPtr Descriptor;
        [MarshalAs(UnmanagedType.Bool)] internal bool InheritHandle;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true,
        EntryPoint = "CreateNamedPipeW")]
    private static extern SafePipeHandle CreateNamedPipe(
        string name, uint openMode, uint pipeMode, uint maxInstances,
        uint outboundBuffer, uint inboundBuffer, uint defaultTimeout,
        ref SecurityAttributes attributes);

    internal static string BuildSddl(string appSidText)
    {
        SecurityIdentifier appSid;
        try
        {
            appSid = new SecurityIdentifier(appSidText);
        }
        catch (ArgumentException)
        {
            throw new InvalidOperationException("App SID denied");
        }
        string sddl = "O:BAG:BAD:P(A;;0x00000002;;;" + appSid.Value +
            ")(A;;GA;;;SY)(A;;GA;;;BA)S:(ML;;NW;;;ME)";
        if (Ea4eProtectedPipeDescriptorScreen.Screen(sddl, appSid.Value)
            != "CANDIDATE:STATIC_ONLY")
            throw new InvalidOperationException("Pipe descriptor denied");
        return sddl;
    }

    internal static uint ProposedOpenMode()
    {
        return PipeAccessInbound | FileFlagOverlapped |
            FileFlagFirstPipeInstance | AccessSystemSecurity;
    }

    internal static string BuildPipeName(Guid ceremonyId, Guid randomId)
    {
        if (ceremonyId == Guid.Empty || randomId == Guid.Empty ||
            ceremonyId == randomId)
            throw new InvalidOperationException("Pipe name identity denied");
        return @"\\.\pipe\ea4e-issuer-" + ceremonyId.ToString("N") +
            "-" + randomId.ToString("N");
    }

    internal static SafePipeHandle Open(string appSidText, Guid ceremonyId,
                                        out string pipeName)
    {
        // Name and descriptor are chosen here, never by the client message.
        string sddl = BuildSddl(appSidText);
        var descriptor = new RawSecurityDescriptor(sddl);
        byte[] bytes = new byte[descriptor.BinaryLength];
        descriptor.GetBinaryForm(bytes, 0);
        IntPtr memory = Marshal.AllocHGlobal(bytes.Length);
        pipeName = null;
        try
        {
            Marshal.Copy(bytes, 0, memory, bytes.Length);
            var attributes = new SecurityAttributes {
                Length = Marshal.SizeOf(typeof(SecurityAttributes)),
                Descriptor = memory,
                InheritHandle = false,
            };
            string name = BuildPipeName(ceremonyId, Guid.NewGuid());
            // Creator must already hold enabled SeSecurityPrivilege; no fallback.
            SafePipeHandle handle = CreateNamedPipe(name, ProposedOpenMode(),
                PipeTypeMessage | PipeReadmodeMessage | PipeRejectRemoteClients,
                1, FrameLimit, FrameLimit, 5000, ref attributes);
            if (handle == null || handle.IsInvalid)
            {
                int error = Marshal.GetLastWin32Error();
                if (handle != null) handle.Dispose();
                throw new InvalidOperationException("Protected pipe creation denied: " +
                    error);
            }
            pipeName = name;
            return handle;
        }
        finally
        {
            Marshal.FreeHGlobal(memory);
        }
    }
}
