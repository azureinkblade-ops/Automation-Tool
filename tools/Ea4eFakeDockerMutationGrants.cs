// Fake-only grant transitions. This class cannot witness an operator or drive Docker.
using System;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

internal sealed class Ea4eFakeDockerMutationGrants
{
    private static readonly Regex Hex64 = new Regex(@"\A[0-9a-f]{64}\z");
    private static readonly Regex Hex40 = new Regex(@"\A[0-9a-f]{40}\z");
    private static readonly Regex Sid = new Regex(@"\AS-[0-9]+(?:-[0-9]+)+\z");
    private readonly Ea4eDockerMutationStoreIdentity store;

    internal Ea4eFakeDockerMutationGrants(Ea4eDockerMutationStoreIdentity store)
    {
        if (store == null)
            throw new ArgumentNullException("store");
        this.store = store;
    }

    private static bool IsAction(string action)
    {
        return action == "network_create" || action == "gateway_create"
            || action == "gateway_start" || action == "kilo_container_create";
    }

    private static string EventHash(params string[] fields)
    {
        using (var sha = SHA256.Create())
        {
            // Each field is length-prefixed so distinct tuples cannot concatenate alike.
            using (var stream = new System.IO.MemoryStream())
            using (var writer = new System.IO.BinaryWriter(stream, Encoding.UTF8))
            {
                foreach (string field in fields)
                    writer.Write(field);
                writer.Flush();
                return BitConverter.ToString(sha.ComputeHash(stream.ToArray()))
                    .Replace("-", "").ToLowerInvariant();
            }
        }
    }

    internal void IssueFake(string grantId, string nonce, string action,
        string attemptId, string requestHash, string predecessorHash,
        string sourceCommit, string operatorSid, long issuedAt, long expiresAt)
    {
        if (grantId == null || !Hex64.IsMatch(grantId)
            || nonce == null || !Hex64.IsMatch(nonce)
            || !IsAction(action)
            || attemptId == null || !Hex64.IsMatch(attemptId)
            || requestHash == null || !Hex64.IsMatch(requestHash)
            || predecessorHash == null || !Hex64.IsMatch(predecessorHash)
            || sourceCommit == null || !Hex40.IsMatch(sourceCommit)
            || operatorSid == null || !Sid.IsMatch(operatorSid)
            || issuedAt <= 0 || expiresAt <= issuedAt
            || expiresAt - issuedAt > 300)
            throw new InvalidOperationException("Fake grant input denied");

        string issue = issuedAt.ToString(CultureInfo.InvariantCulture);
        string expiry = expiresAt.ToString(CultureInfo.InvariantCulture);
        string eventHash = EventHash("ISSUE", grantId, nonce, action,
            attemptId, requestHash, predecessorHash, sourceCommit,
            operatorSid, issue, expiry);
        store.RecordFakeTransition(eventHash, delegate(Ea4eProtectedSqlite db)
        {
            using (var insert = db.Prepare(
                "INSERT INTO mutation_fake_grants VALUES (?,?,?,?,?,?,?,?,?,?,?)"))
            {
                string[] values = { grantId, nonce, action, attemptId,
                    requestHash, predecessorHash, sourceCommit, operatorSid,
                    issue, expiry, "ISSUED" };
                for (int index = 0; index < values.Length; index++)
                    insert.BindText(index + 1, values[index]);
                if (insert.Step())
                    throw new InvalidOperationException("Fake grant insert denied");
            }
        });
    }

    internal void ClaimFake(string grantId, string action, string attemptId,
        string requestHash, string predecessorHash, long now)
    {
        if (grantId == null || !Hex64.IsMatch(grantId)
            || !IsAction(action)
            || attemptId == null || !Hex64.IsMatch(attemptId)
            || requestHash == null || !Hex64.IsMatch(requestHash)
            || predecessorHash == null || !Hex64.IsMatch(predecessorHash)
            || now <= 0)
            throw new InvalidOperationException("Fake claim input denied");

        string time = now.ToString(CultureInfo.InvariantCulture);
        string eventHash = EventHash("CLAIM", grantId, action, attemptId,
            requestHash, predecessorHash, time);
        store.RecordFakeTransition(eventHash, delegate(Ea4eProtectedSqlite db)
        {
            using (var read = db.Prepare(
                "SELECT action,attempt_id,request_hash,predecessor_hash," +
                "issued_at,expires_at,state FROM mutation_fake_grants " +
                "WHERE grant_id=?"))
            {
                read.BindText(1, grantId);
                if (!read.Step() || read.Text(0) != action
                    || read.Text(1) != attemptId
                    || read.Text(2) != requestHash
                    || read.Text(3) != predecessorHash
                    || Int64.Parse(read.Text(4), CultureInfo.InvariantCulture) > now
                    || Int64.Parse(read.Text(5), CultureInfo.InvariantCulture) <= now
                    || read.Text(6) != "ISSUED")
                    throw new InvalidOperationException("Fake claim denied");
                if (read.Step())
                    throw new InvalidOperationException("Fake grant duplicate denied");
            }
            using (var update = db.Prepare(
                "UPDATE mutation_fake_grants SET state='CLAIMED' " +
                "WHERE grant_id=? AND state='ISSUED'"))
            {
                update.BindText(1, grantId);
                if (update.Step())
                    throw new InvalidOperationException("Fake claim update denied");
            }
        });
    }

    internal void RevokeFake(string grantId)
    {
        if (grantId == null || !Hex64.IsMatch(grantId))
            throw new InvalidOperationException("Fake revoke input denied");
        string eventHash = EventHash("REVOKE", grantId);
        store.RecordFakeTransition(eventHash, delegate(Ea4eProtectedSqlite db)
        {
            using (var read = db.Prepare(
                "SELECT state FROM mutation_fake_grants WHERE grant_id=?"))
            {
                read.BindText(1, grantId);
                if (!read.Step() || read.Text(0) != "ISSUED" || read.Step())
                    throw new InvalidOperationException("Fake revoke denied");
            }
            using (var update = db.Prepare(
                "UPDATE mutation_fake_grants SET state='REVOKED' WHERE grant_id=?"))
            {
                update.BindText(1, grantId);
                if (update.Step())
                    throw new InvalidOperationException("Fake revoke update denied");
            }
        });
    }
}
