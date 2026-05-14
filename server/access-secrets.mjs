import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

export function createAccessPasswordCodec(secret) {
  const key = createHash("sha256").update(secret).digest();

  return {
    encrypt(password) {
      if (!password) {
        return "";
      }
      const iv = randomBytes(12);
      const cipher = createCipheriv("aes-256-gcm", key, iv);
      const encrypted = Buffer.concat([cipher.update(String(password), "utf8"), cipher.final()]);
      const tag = cipher.getAuthTag();
      return ["v1", iv.toString("base64url"), tag.toString("base64url"), encrypted.toString("base64url")].join(":");
    },

    decrypt(encryptedPassword) {
      const [version, ivValue, tagValue, encryptedValue] = String(encryptedPassword || "").split(":");
      if (version !== "v1" || !ivValue || !tagValue || !encryptedValue) {
        return "";
      }
      try {
        const decipher = createDecipheriv("aes-256-gcm", key, Buffer.from(ivValue, "base64url"));
        decipher.setAuthTag(Buffer.from(tagValue, "base64url"));
        return Buffer.concat([
          decipher.update(Buffer.from(encryptedValue, "base64url")),
          decipher.final(),
        ]).toString("utf8");
      } catch {
        return "";
      }
    },
  };
}
