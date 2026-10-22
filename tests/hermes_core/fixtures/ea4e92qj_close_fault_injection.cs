// Inert dependencies for the exact unwired owner source. No native call occurs.
using System;

internal static class Ea4eDirectoryInstallPlanCandidate
{
    internal const uint DirectoryReadbackAccess = 0x012200a1;
    internal const uint ShareReadWriteNoDelete = 3;
    internal const uint DisallowPathRedirects = 1;

    internal static string Build(string parent, string manifest, string sid,
        out string[] components, out string sddl)
    {
        components = new[] { @"C:\ProgramData\Hermes", "", "", "" };
        sddl = "pinned-test-descriptor";
        return null;
    }
}

internal static class Ea4eDirectory2SecurityAttributesCandidate
{
    internal static bool ReturnDenialAfterObserver;

    internal static string Inspect(string sddl, string sid,
        Func<IntPtr, string> observer)
    {
        string result = observer(IntPtr.Zero);
        return ReturnDenialAfterObserver ? "DENY:INSPECT_AFTER_OBSERVER" : result;
    }
}

internal static class Ea4eDirectory2NativeAbiCandidate
{
    internal static int Calls;

    internal static IntPtr InvokeUnwired(string path, uint access, uint share,
        uint flags, IntPtr attributes, out int lastError)
    {
        Calls++;
        lastError = 0;
        return new IntPtr(123);
    }
}

internal static class Ea4eDirectory2HandleResultCandidate
{
    internal static string Screen(IntPtr raw)
    {
        return "CANDIDATE:NON_SENTINEL_ONLY";
    }
}

internal sealed class Ea4eDirectoryObservedHandleCandidate : IDisposable
{
    internal static int Disposals;
    internal static bool ThrowOnDispose;

    internal Ea4eDirectoryObservedHandleCandidate(IntPtr raw) { }
    internal bool ReleaseObserved { get { return false; } }
    internal int ReleaseError { get { return 0; } }

    public void Dispose()
    {
        Disposals++;
        if (ThrowOnDispose) throw new InvalidOperationException("inert close fault");
    }
}

internal static class Ea4eDirectory2RetainedShapeCandidate
{
    internal static bool Deny;

    internal static string Read(Ea4eDirectoryObservedHandleCandidate handle,
        string path, out string volume, out string fileId)
    {
        volume = "volume-observed";
        fileId = "file-observed";
        return Deny ? "DENY:SHAPE" : "CANDIDATE:RETAINED_DIRECTORY_SHAPE_ONLY";
    }
}

internal static class Ea4eAnnouncementFileDescriptorCandidate
{
    internal static string ReadDirectory(Ea4eDirectoryObservedHandleCandidate handle,
        string sid, out byte[] descriptor)
    {
        descriptor = new byte[0];
        return "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY";
    }
}

internal static class Ea4e92qjCloseFaultInjection
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        Ea4eDirectory2RetainedShapeCandidate.Deny = args[0] == "owned-throw";
        Ea4eDirectory2SecurityAttributesCandidate.ReturnDenialAfterObserver =
            args[0] == "accepted-throw";
        Ea4eDirectoryObservedHandleCandidate.ThrowOnDispose = true;
        if (!Ea4eDirectory2RetainedShapeCandidate.Deny &&
            !Ea4eDirectory2SecurityAttributesCandidate.ReturnDenialAfterObserver)
            return 2;

        Ea4eDirectoryObservedHandleCandidate retained;
        int lastError, closeError;
        string observation, close, volume, fileId;
        string disposition = Ea4eDirectory2OneAttemptCandidate.AttemptUnwired(
            @"C:\ProgramData", @"C:\ProgramData\Hermes\EA4E", @"C:\ProgramData\Hermes",
            "S-1-5-21-1-2-3-1001", "pinned-test-descriptor",
            Ea4eDirectoryInstallPlanCandidate.DirectoryReadbackAccess,
            Ea4eDirectoryInstallPlanCandidate.ShareReadWriteNoDelete,
            Ea4eDirectoryInstallPlanCandidate.DisallowPathRedirects,
            out retained, out lastError, out closeError,
            out observation, out close, out volume, out fileId);

        Console.WriteLine(String.Join("|", new[] {
            disposition, observation, close, Ea4eDirectory2NativeAbiCandidate.Calls.ToString(),
            Ea4eDirectoryObservedHandleCandidate.Disposals.ToString(),
            retained == null ? "NO_RETAINED" : "RETAINED", volume, fileId
        }));
        return 0;
    }
}
