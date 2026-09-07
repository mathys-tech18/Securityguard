"""
Bot de vérification Discord — WinterArc
---------------------------------------
- Les nouveaux arrivants ne voient QUE le salon de vérification.
- Tout message envoyé dans ce salon est supprimé automatiquement.
- Si le message est le bon mot de passe : le membre reçoit les rôles
  et le salon de vérification disparaît pour lui.

Installation :
    pip install -U discord.py python-dotenv

Lancement :
    DISCORD_TOKEN=ton_token python bot_verification.py
"""

import os
import asyncio
import logging

import discord
from discord.ext import commands

# ---------------------------------------------------------------- CONFIG ----

VERIF_CHANNEL_ID = 1546541757704175687   # salon de vérification
MEMBER_ROLE_ID   = 1546542012344434698   # rôle membre
VERIFIED_ROLE_ID = 1546542172638289920   # rôle vérifié

PASSWORD = "WinterArc"
CASE_SENSITIVE = True        # False => "winterarc" marche aussi
WRONG_MSG_DELAY = 5          # secondes avant suppression du message d'erreur

TOKEN = "MTU0NjU0MjkxMzc1MDU3MzA4Ng.GcMINW.TUoa5XLI_NZN48AIFmGLyyxoBvIqNHk9_xIpgg"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("winterarc")

# ------------------------------------------------------------------- BOT ----

intents = discord.Intents.default()
intents.message_content = True   # à activer dans le Developer Portal
intents.members = True           # idem

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def build_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔒 Vérification requise",
        description=(
            "**Entrez le bon mot de passe** pour accéder au serveur.\n\n"
            "Écrivez-le simplement dans ce salon. Votre message sera "
            "supprimé immédiatement.\n"
            "Si le mot de passe est correct, vous recevrez vos rôles et "
            "ce salon disparaîtra."
        ),
        color=0x2B6CB0,
    )
    embed.set_footer(text="WinterArc • Système de vérification")
    return embed


@bot.event
async def on_ready():
    log.info("Connecté en tant que %s (%s)", bot.user, bot.user.id)
    channel = bot.get_channel(VERIF_CHANNEL_ID)
    if channel is None:
        log.warning("Salon %s introuvable — vérifie l'ID et les permissions.",
                    VERIF_CHANNEL_ID)


@bot.event
async def on_message(message: discord.Message):
    # Ignore les bots et les MP
    if message.author.bot or message.guild is None:
        return

    # Hors du salon de vérification : comportement normal
    if message.channel.id != VERIF_CHANNEL_ID:
        await bot.process_commands(message)
        return

    # Laisse passer les commandes admin dans le salon (!setup, !setup_perms)
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    content = message.content.strip()

    # Suppression systématique
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        log.warning("Impossible de supprimer un message dans le salon de vérif.")

    ok = content == PASSWORD if CASE_SENSITIVE else content.casefold() == PASSWORD.casefold()

    if not ok:
        try:
            await message.channel.send(
                f"{message.author.mention} ❌ Mot de passe incorrect.",
                delete_after=WRONG_MSG_DELAY,
            )
        except discord.HTTPException:
            pass
        return

    # ---- Mot de passe correct ----
    await verify_member(message.author, message.channel)


async def verify_member(member: discord.Member, channel: discord.abc.Messageable):
    guild = member.guild
    roles = [
        r for r in (guild.get_role(MEMBER_ROLE_ID), guild.get_role(VERIFIED_ROLE_ID))
        if r is not None and r not in member.roles
    ]

    if not roles:
        return

    try:
        await member.add_roles(*roles, reason="Vérification WinterArc réussie")
    except discord.Forbidden:
        log.error("Permissions insuffisantes pour donner les rôles à %s. "
                  "Place le rôle du bot AU-DESSUS des rôles à attribuer.", member)
        return
    except discord.HTTPException as e:
        log.error("Erreur en attribuant les rôles : %s", e)
        return

    log.info("%s vérifié.", member)

    # Filet de sécurité : masque le salon même si les permissions du rôle
    # vérifié ne sont pas configurées (voir !setup_perms).
    try:
        await channel.set_permissions(
            member, view_channel=False,
            reason="Vérification terminée",
        )
    except (discord.Forbidden, discord.HTTPException):
        pass

    # Confirmation en MP (le salon n'est plus visible pour lui)
    try:
        await member.send(
            f"✅ Vérification réussie sur **{guild.name}** ! "
            "Tu as désormais accès au serveur."
        )
    except discord.Forbidden:
        pass  # MP fermés


# -------------------------------------------------------------- COMMANDES ---

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_cmd(ctx: commands.Context):
    """Poste le message de vérification dans le salon."""
    channel = bot.get_channel(VERIF_CHANNEL_ID)
    if channel is None:
        return await ctx.send("Salon de vérification introuvable.", delete_after=10)
    await channel.send(embed=build_embed())
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass


@bot.command(name="setup_perms")
@commands.has_permissions(administrator=True)
async def setup_perms(ctx: commands.Context):
    """Configure les permissions du salon de vérification."""
    channel = bot.get_channel(VERIF_CHANNEL_ID)
    if channel is None:
        return await ctx.send("Salon introuvable.", delete_after=10)

    verified = ctx.guild.get_role(VERIFIED_ROLE_ID)

    await channel.set_permissions(
        ctx.guild.default_role,
        view_channel=True, send_messages=True,
        read_message_history=False, add_reactions=False,
    )
    if verified:
        await channel.set_permissions(verified, view_channel=False)

    await ctx.send(
        "✅ Permissions du salon de vérification configurées.\n"
        "Pense à mettre **@everyone → Voir le salon : ❌** sur tous les autres "
        "salons, et **@Membre → ✅**.",
        delete_after=30,
    )


@bot.command(name="verify")
@commands.has_permissions(manage_roles=True)
async def manual_verify(ctx: commands.Context, member: discord.Member):
    """Vérifie manuellement un membre : !verify @pseudo"""
    await verify_member(member, ctx.channel)
    await ctx.send(f"✅ {member.mention} vérifié manuellement.", delete_after=10)


@setup_cmd.error
@setup_perms.error
@manual_verify.error
async def perms_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔ Tu n'as pas la permission.", delete_after=5)


# ------------------------------------------------------------------ START ---

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Définis la variable d'environnement DISCORD_TOKEN.")
    bot.run(TOKEN)