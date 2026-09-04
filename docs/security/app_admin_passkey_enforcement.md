# app_admin パスキー強制化の運用方針

## 認証方針

強制化された `app_admin` は、通常ログインでパスワードの後に有効なWebAuthn credentialを使う。合言葉とTOTPは通常ログインおよびパスキーの代替経路として扱わない。

強制化は有効なcredentialが2件以上ある場合だけ実行できる。platform authenticatorとhardware security keyの組み合わせを許可し、特定の生体認証方式は要求しない。WebAuthnの `userVerification=required` とUP/UVの検証結果をサーバー側で確認する。

## step-up

高リスク操作では、通常のaccess Cookieとは別に、直近のUV付きWebAuthn検証で発行された短命JWTを `X-Step-Up-Token` ヘッダーで送信する。step-up JWTの有効期間は5分で、通常セッションの代用にはならない。

現在の適用先は次のとおり。

- credentialの失効
- 全スタッフへのお知らせ送信
- 問い合わせの更新・返信・削除

強制化前のapp_adminには既存の操作互換性を残す。

## ロールバックと廃止

緊急時は、運用管理者がDBバックアップと監査記録を確認したうえで `staffs.passkey_enforced_at` をNULLに戻し、対象アカウントの有効credentialを確認する。通常の変更手順として直接SQLを配布せず、管理コマンドまたは承認済みmigrationで実施する。

合言葉設定スクリプト、TOTPのapp_admin通常ログイン経路、関連UI・テストは、break-glass検証とフロントエンド移行完了後に削除する。削除前に、強制化済みアカウントのcredential件数、直近のstep-up成功、break-glass復旧手順を監査し、復旧確認が取れない場合は削除を延期する。
