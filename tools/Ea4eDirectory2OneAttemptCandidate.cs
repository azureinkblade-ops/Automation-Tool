// Unwired source candidate. No production entry point invokes this owner.
using System;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eDirectory2OneAttemptCandidate
{
    private const string ShapeCandidate = "CANDIDATE:RETAINED_DIRECTORY_SHAPE_ONLY";
    private const string DescriptorCandidate = "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY";

    internal static string ScreenInputs(string path, string appSid, string sddl,
                                        uint access, uint share, uint flags)
    {
        if (String.IsNullOrEmpty(path) || String.IsNullOrEmpty(appSid) ||
            String.IsNullOrEmpty(sddl)) return "DENY:INPUT";
        if (access != Ea4eDirectoryInstallPlanCandidate.DirectoryReadbackAccess ||
            share != Ea4eDirectoryInstallPlanCandidate.ShareReadWriteNoDelete ||
            flags != Ea4eDirectoryInstallPlanCandidate.DisallowPathRedirects)
            return "DENY:NATIVE_POLICY";
        if (Ea4eAnnouncementFileDescriptorCandidate.ScreenDirectorySddl(
                sddl, appSid) != DescriptorCandidate)
            return "DENY:DESCRIPTOR";
        return null;
    }

    // The caller must separately authenticate the parent, manifest, SID,
    // volume, privilege, and absence. A candidate result is not installation.
    internal static string AttemptUnwired(string path, string appSid, string sddl,
        uint access, uint share, uint flags, out SafeFileHandle retained,
        out int lastError, out string volumeHex, out string fileIdHex)
    {
        retained = null;
        lastError = 0;
        volumeHex = null;
        fileIdHex = null;
        string denial = ScreenInputs(path, appSid, sddl, access, share, flags);
        if (denial != null) return denial;

        SafeFileHandle owned = null;
        SafeFileHandle accepted = null;
        int observedError = 0;
        string observedVolume = null, observedId = null;
        try
        {
            string result = Ea4eDirectory2SecurityAttributesCandidate.Inspect(sddl, appSid,
                attributes => {
                    IntPtr raw = Ea4eDirectory2NativeAbiCandidate.InvokeUnwired(
                        path, access, share, flags, attributes, out observedError);
                    if (Ea4eDirectory2HandleResultCandidate.Screen(raw) !=
                        "CANDIDATE:NON_SENTINEL_ONLY")
                        return "DENY:NATIVE_RESULT_UNCERTAIN";
                    owned = new SafeFileHandle(raw, true);
                    string shape = Ea4eDirectory2RetainedShapeCandidate.Read(
                        owned, path, out observedVolume, out observedId);
                    if (shape != ShapeCandidate) return shape;
                    byte[] descriptor;
                    string readback = Ea4eAnnouncementFileDescriptorCandidate.ReadDirectory(
                        owned, appSid, out descriptor);
                    if (readback != DescriptorCandidate)
                        return readback;
                    accepted = owned;
                    owned = null;
                    return "CANDIDATE:RETAINED_DIRECTORY_READBACK_ONLY";
                });
            lastError = observedError;
            if (result == "CANDIDATE:RETAINED_DIRECTORY_READBACK_ONLY")
            {
                retained = accepted;
                volumeHex = observedVolume;
                fileIdHex = observedId;
                accepted = null;
            }
            return result;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:ATTEMPT_UNCERTAIN";
        }
        finally
        {
            if (owned != null) owned.Dispose();
            if (accepted != null) accepted.Dispose();
        }
    }
}
