# Backup and Recovery Plan

## Objectives

- Preserve patient, coupon, consent, delivery, and audit records.
- Restore the pilot after device failure, database corruption, deployment error, or accidental deletion.
- Keep backups confidential and separate from the running application.

## Minimum pilot procedure

1. Create an encrypted database backup before launch.
2. Create another backup before every migration or deployment.
3. Schedule at least one automatic daily backup.
4. Copy backups to a separate protected destination.
5. Retain a rolling 30-day set unless the approved policy says otherwise.
6. Record backup time, size, checksum, and result without patient data.
7. Test restoration into an isolated location before Saturday.

For Railway, keep PostgreSQL on private networking and verify the platform backup capability available to the selected plan. Maintain a separate encrypted export outside the running Railway project so provider or project-level failure does not remove the only recovery copy.

## Recovery targets

- Proposed recovery point: no more than 24 hours of data loss
- Proposed recovery time: restore clinic operations within two hours

These targets must be revised if campaign volume makes them insufficient.

## Restore test

1. Prepare an isolated application instance.
2. Verify backup checksum and decrypt it.
3. Restore the database and required protected QR assets.
4. Start the application without contacting real recipients.
5. Verify login, patient search, coupon validation, and redeemed states.
6. Confirm migrations match the restored database.
7. Record the test date, operator, backup ID, result, and problems.
8. Securely remove the temporary restored copy after verification.

## Safety rules

- Never overwrite the only production database during a restore test.
- Never store the encryption key beside the encrypted backup.
- Never place backups in source control, public cloud folders, or unprotected removable media.
- Restrict backup and restore commands to the designated operator.
- Verify the exact source and destination before any replacement operation.
