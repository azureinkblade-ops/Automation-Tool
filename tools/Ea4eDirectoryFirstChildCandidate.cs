// Fake-port first-child control flow; no native install adapter is wired.
using System;

internal interface IEa4eDirectoryFirstChildPort
{
    string ScreenParent(string programDataPath);
    string Create(string exactChildPath, string sddl, uint access,
                  uint share, uint flags, out IDisposable retainedHandle);
    string ScreenCreated(IDisposable retainedHandle, string exactChildPath,
                         string sddl);
}

internal static class Ea4eDirectoryFirstChildCandidate
{
    internal static string Attempt(string resolvedProgramData,
                                   string pinnedManifestRoot, string appSid,
                                   IEa4eDirectoryFirstChildPort port)
    {
        IDisposable retained;
        string result = AttemptAndRetain(resolvedProgramData,
            pinnedManifestRoot, appSid, port, out retained);
        try
        {
            if (retained != null) retained.Dispose();
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:PORT_UNCERTAIN";
        }
        return result;
    }

    internal static string AttemptAndRetain(string resolvedProgramData,
                                            string pinnedManifestRoot,
                                            string appSid,
                                            IEa4eDirectoryFirstChildPort port,
                                            out IDisposable retainedHandle)
    {
        retainedHandle = null;
        if (port == null) return "DENY:PORT_MISSING";
        string[] paths;
        string sddl;
        string denial = Ea4eDirectoryInstallPlanCandidate.Build(
            resolvedProgramData, pinnedManifestRoot, appSid,
            out paths, out sddl);
        if (denial != null) return denial;
        try
        {
            denial = port.ScreenParent(resolvedProgramData);
            if (denial != null) return "DENY:PARENT_" + denial;
            IDisposable created = null;
            try
            {
                denial = port.Create(paths[0], sddl,
                    Ea4eDirectoryInstallPlanCandidate.DirectoryReadbackAccess,
                    Ea4eDirectoryInstallPlanCandidate.ShareReadWriteNoDelete,
                    Ea4eDirectoryInstallPlanCandidate.DisallowPathRedirects,
                    out created);
                if (denial != null) return "DENY:CREATE_" + denial;
                if (created == null) return "DENY:CREATE_HANDLE_MISSING";
                denial = port.ScreenCreated(created, paths[0], sddl);
                if (denial != null) return "DENY:CREATED_" + denial;
                retainedHandle = created;
                created = null;
                return "CANDIDATE:FIRST_CHILD_FAKE_ONLY";
            }
            finally
            {
                if (created != null) created.Dispose();
            }
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:PORT_UNCERTAIN";
        }
    }
}
