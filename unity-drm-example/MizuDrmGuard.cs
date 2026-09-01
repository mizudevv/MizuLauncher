using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public sealed class MizuDrmGuard : MonoBehaviour
{
    [Header("Must match the launcher/game configuration")]
    [SerializeField] private string gameId = "YOUR-GAME-ID";
    [SerializeField] private string gameSecret = "CHANGE_ME_TO_THE_SAME_SECRET_USED_BY_LAUNCHER";
    [SerializeField] private string verifyFunctionUrl = "https://YOUR_PROJECT.supabase.co/functions/v1/mizu-drm-verify";

    private void Awake()
    {
        DontDestroyOnLoad(gameObject);
    }

    private void Start()
    {
        StartCoroutine(VerifyBeforeGameStarts());
    }

    private IEnumerator VerifyBeforeGameStarts()
    {
        GrantPayload grant;
        try
        {
            grant = ReadAndDecryptGrant();
        }
        catch
        {
            Application.Quit();
            yield break;
        }

        string json = JsonUtility.ToJson(new VerifyRequest
        {
            game_id = gameId,
            user_id = grant.user_id,
            token = grant.token,
        });

        using (UnityWebRequest request = new UnityWebRequest(verifyFunctionUrl, "POST"))
        {
            byte[] body = Encoding.UTF8.GetBytes(json);
            request.uploadHandler = new UploadHandlerRaw(body);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                Application.Quit();
                yield break;
            }

            VerifyResponse response;
            try
            {
                response = JsonUtility.FromJson<VerifyResponse>(request.downloadHandler.text);
            }
            catch
            {
                response = null;
            }

            if (response == null || !response.authorized)
                Application.Quit();
        }
    }

    private string GrantPath()
    {
        string installRoot = Directory.GetParent(Application.dataPath).FullName;
        return Path.Combine(installRoot, "mizuapi.dat");
    }

    private GrantPayload ReadAndDecryptGrant()
    {
        string path = GrantPath();
        if (!File.Exists(path)) throw new Exception("mizuapi.dat missing");

        string encoded = File.ReadAllText(path).Trim();
        byte[] packed = Convert.FromBase64String(encoded.Replace('-', '+').Replace('_', '/'));
        if (packed.Length < 28) throw new Exception("invalid DRM file");

        byte[] nonce = new byte[12];
        Buffer.BlockCopy(packed, 0, nonce, 0, 12);

        int cipherLen = packed.Length - 12 - 16;
        byte[] ciphertext = new byte[cipherLen];
        byte[] tag = new byte[16];
        Buffer.BlockCopy(packed, 12, ciphertext, 0, cipherLen);
        Buffer.BlockCopy(packed, packed.Length - 16, tag, 0, 16);

        // Educational DRM: a determined reverse engineer can extract this key from the game.
        // Its purpose is to prevent casual copying/stale file reuse, not to be unbreakable.
        byte[] key = SHA256.HashData(Encoding.UTF8.GetBytes($"mizulauncher-drm:{gameSecret}:{gameId}"));
        byte[] plaintext = new byte[cipherLen];

        using (AesGcm aes = new AesGcm(key, 16))
        {
            aes.Decrypt(nonce, ciphertext, tag, plaintext, Encoding.UTF8.GetBytes(gameId));
        }

        GrantPayload grant = JsonUtility.FromJson<GrantPayload>(Encoding.UTF8.GetString(plaintext));
        if (grant == null || grant.game_id != gameId || string.IsNullOrWhiteSpace(grant.user_id) || string.IsNullOrWhiteSpace(grant.token))
            throw new Exception("invalid grant payload");

        if (DateTime.TryParse(grant.expires_at, out DateTime expiry) && expiry.ToUniversalTime() <= DateTime.UtcNow)
            throw new Exception("DRM grant expired");

        if (!string.Equals(grant.status, "authorized", StringComparison.OrdinalIgnoreCase))
            throw new Exception("DRM status blocked");

        return grant;
    }

    [Serializable]
    private sealed class GrantPayload
    {
        public int version;
        public string game_id;
        public string user_id;
        public string token;
        public string expires_at;
        public string status;
    }

    [Serializable]
    private sealed class VerifyRequest
    {
        public string game_id;
        public string user_id;
        public string token;
    }

    [Serializable]
    private sealed class VerifyResponse
    {
        public bool ok;
        public bool authorized;
        public string status;
    }
}
