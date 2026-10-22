// Unwired source candidate. No production entry point invokes this owner.
using System;
using System.Runtime.InteropServices;

internal static class Ea4eDirectory2OneAttemptCandidate
{
    private const string ShapeCandidate = "CANDIDATE:RETAINED_DIRECTORY_SHAPE_ONLY";
    private const string DescriptorCandidate = "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY";

    [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    internal static string ClassifyUncertain(bool attempted,
                                             bool rawCloseFailed)
    {
        if (rawCloseFailed) return "DENY:RAW_HANDLE_CLOSE_UNCERTAIN";
        return attempted ? "DENY:POST_CALL_UNCERTAIN" :
            "DENY:PRE_CALL_UNAVAILABLE";
    }

    internal static string ClassifyRelease(bool observed)
    {
        return observed ? null : "DENY:WRAPPER_CLOSE_UNCERTAIN";
    }

    internal static string ClassifyDisposition(bool attempted, bool retained)
    {
        return attempted && !retained
            ? "DENY:POST_ATTEMPT_RECONCILIATION_REQUIRED" : null;
    }

    internal static string ScreenInputs(string resolvedProgramData,
        string pinnedManifestRoot, string path, string appSid, string sddl,
        uint access, uint share, uint flags)
    {
        if (String.IsNullOrEmpty(path) || String.IsNullOrEmpty(appSid) ||
            String.IsNullOrEmpty(sddl)) return "DENY:INPUT";
        if (access != Ea4eDirectoryInstallPlanCandidate.DirectoryReadbackAccess ||
            share != Ea4eDirectoryInstallPlanCandidate.ShareReadWriteNoDelete ||
            flags != Ea4eDirectoryInstallPlanCandidate.DisallowPathRedirects)
            return "DENY:NATIVE_POLICY";
        string[] components;
        string plannedSddl;
        string plan = Ea4eDirectoryInstallPlanCandidate.Build(
            resolvedProgramData, pinnedManifestRoot, appSid,
            out components, out plannedSddl);
        if (plan != null) return plan;
        if (components == null || components.Length != 4 ||
            !String.Equals(path, components[0],
                           StringComparison.OrdinalIgnoreCase))
            return "DENY:FIRST_CHILD_PATH";
        if (!String.Equals(sddl, plannedSddl, StringComparison.Ordinal))
            return "DENY:DESCRIPTOR_MISMATCH";
        return null;
    }

    // The caller must separately authenticate the parent, manifest, SID,
    // volume, privilege, and absence. Close success does not reconcile a path.
    internal static string AttemptUnwired(string resolvedProgramData,
        string pinnedManifestRoot, string path, string appSid, string sddl,
        uint access, uint share, uint flags,
        out Ea4eDirectoryObservedHandleCandidate retained,
        out int lastError, out int closeError,
        out string observationStatus, out string closeStatus,
        out string volumeHex, out string fileIdHex)
    {
        retained = null;
        lastError = 0;
        closeError = 0;
        observationStatus = null;
        closeStatus = "NOT_ATTEMPTED";
        volumeHex = null;
        fileIdHex = null;
        string denial = ScreenInputs(resolvedProgramData, pinnedManifestRoot,
            path, appSid, sddl, access, share, flags);
        if (denial != null)
        {
            observationStatus = denial;
            return denial;
        }

        Ea4eDirectoryObservedHandleCandidate owned = null;
        Ea4eDirectoryObservedHandleCandidate accepted = null;
        int observedError = 0;
        int observedCloseError = 0;
        bool attempted = false, rawCloseFailed = false;
        bool wrapperCloseUncertain = false;
        string observedVolume = null, observedId = null;
        string observedCloseStatus = "NOT_ATTEMPTED";
        string result = null;
        try
        {
            result = Ea4eDirectory2SecurityAttributesCandidate.Inspect(sddl, appSid,
                attributes => {
                    attempted = true;
                    IntPtr raw = Ea4eDirectory2NativeAbiCandidate.InvokeUnwired(
                        path, access, share, flags, attributes, out observedError);
                    if (raw == IntPtr.Zero || raw == new IntPtr(-1))
                        return "DENY:NATIVE_RESULT_UNCERTAIN";
                    bool transferred = false;
                    try
                    {
                        if (Ea4eDirectory2HandleResultCandidate.Screen(raw) !=
                            "CANDIDATE:NON_SENTINEL_ONLY")
                            return "DENY:NATIVE_RESULT_UNCERTAIN";
                        owned = new Ea4eDirectoryObservedHandleCandidate(raw);
                        transferred = true;
                    }
                    finally
                    {
                        if (!transferred)
                        {
                            rawCloseFailed = true;
                            observedCloseStatus = "DENY:RAW_HANDLE_CLOSE_UNCERTAIN";
                            bool closed = CloseHandle(raw);
                            observedCloseError = closed ? 0 : Marshal.GetLastWin32Error();
                            if (closed)
                            {
                                rawCloseFailed = false;
                                observedCloseStatus = "CANDIDATE:RAW_CLOSED";
                            }
                            if (!closed)
                                throw new InvalidOperationException(
                                    "Raw directory handle close failed");
                        }
                    }
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
            if (result == "CANDIDATE:RETAINED_DIRECTORY_READBACK_ONLY")
            {
                retained = accepted;
                volumeHex = observedVolume;
                fileIdHex = observedId;
                accepted = null;
                observedCloseStatus = "RETAINED_BY_CALLER";
            }
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            result = ClassifyUncertain(attempted, rawCloseFailed);
        }
        finally
        {
            lastError = observedError;
            if (owned != null)
            {
                bool closeThrew = false;
                try { owned.Dispose(); }
                catch (Exception error)
                {
                    if (error is OutOfMemoryException || error is StackOverflowException)
                        throw;
                    closeThrew = true;
                }
                bool closed = !closeThrew && owned.ReleaseObserved;
                wrapperCloseUncertain |= !closed;
                observedCloseStatus = wrapperCloseUncertain ?
                    ClassifyRelease(false) : "CANDIDATE:WRAPPER_CLOSED";
                if (!closed)
                    observedCloseError = owned.ReleaseError;
            }
            if (accepted != null)
            {
                bool closeThrew = false;
                try { accepted.Dispose(); }
                catch (Exception error)
                {
                    if (error is OutOfMemoryException || error is StackOverflowException)
                        throw;
                    closeThrew = true;
                }
                bool closed = !closeThrew && accepted.ReleaseObserved;
                wrapperCloseUncertain |= !closed;
                observedCloseStatus = wrapperCloseUncertain ?
                    ClassifyRelease(false) : "CANDIDATE:WRAPPER_CLOSED";
                if (!closed)
                    observedCloseError = accepted.ReleaseError;
            }
            closeError = observedCloseError;
            closeStatus = observedCloseStatus;
        }
        observationStatus = result;
        bool acceptedResult = result == "CANDIDATE:RETAINED_DIRECTORY_READBACK_ONLY" &&
            retained != null && !wrapperCloseUncertain;
        string disposition = ClassifyDisposition(attempted, acceptedResult);
        if (disposition != null)
        {
            volumeHex = observedVolume;
            fileIdHex = observedId;
            return disposition;
        }
        return result;
    }
}
