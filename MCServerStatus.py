'''Written by Cael Shoop.'''

import os
import json
import asyncio
import discord
import datetime
from typing import Literal
from discord import (
    app_commands,
    ButtonStyle,
    Client,
    Color,
    Embed,
    Guild,
    Intents,
    Interaction,
    Message,
    TextChannel,
    utils,
)
from discord.ext import tasks
from dotenv import load_dotenv
from mcstatus import JavaServer


load_dotenv()


class MCServer:
    def __init__(self, name:str, address:str, message:Message = None):
        self.name = name
        self.address = address
        self.guild:Guild = None
        self.channel:TextChannel = None
        self.message = message
        if self.message:
            self.channel = self.message.channel
            self.guild = self.message.guild
        self.server = JavaServer.lookup(self.address)

    async def make_message(self, channel:TextChannel):
        if self.message:
            return
        try:
            content = self.get_content()
            self.message = await channel.send(content=content)
            self.channel = self.message.channel
            self.guild = self.message.guild
        except Exception as e:
            await self.handle_exception(e)

    async def get_status(self):
        try:
            content = self.get_content()
            await self.message.edit(content=content)
        except Exception as e:
            await self.handle_exception(e)

    def get_content(self):
        status = self.server.status()
        content = f'{self.name} is **online** with {status.players.online} online player'
        if status.players.online == 0:
            content += 's.'
        else:
            if status.players.online == 1:
                content += '.\n\nPlayer:\n'
            else:
                content += 's.\n\nPlayers:\n'
            for player in status.players.sample:
                content += f'{player.name}\n'
        return content

    async def handle_exception(self, e):
        await self.message.edit(content=f'{self.name} is **offline**: {e}')
        print(f'{get_log_time()}> Error looking up server {self.name} ({self.address}) status: {e}')


class MCStatusClient(Client):
    FILE_PATH = 'info.json'

    def __init__(self, intents):
        super(MCStatusClient, self).__init__(intents=intents)
        self.servers = []
        self.tree: app_commands.CommandTree = app_commands.CommandTree(self)

    async def read_json_file(self):
        if not os.path.exists(self.FILE_PATH):
            print(f'{get_log_time()}> {self.FILE_PATH} does not exist yet')
            return
        with open(self.FILE_PATH, "r", encoding="utf-8") as file:
            print(f"{get_log_time()}> Reading {self.FILE_PATH}")
            data = json.load(file)
            for item in data:
                found = False
                for server in self.servers:
                    if server.name == item['name'] and server.address == item['address']:
                        found = True
                        print(f'{get_log_time()}> Recognized server {item["name"]} with message id {item["message_id"]}')
                if not found:
                    try:
                        guild = self.get_guild(item['guild_id'])
                        channel = guild.get_channel(item['channel_id'])
                        message = await channel.fetch_message(item['message_id'])
                        server = MCServer(item['name'], item['address'], message=message)
                        self.servers.append(server)
                        print(f'{get_log_time()}> Recovered server {item["name"]} with message id {item["message_id"]}')
                    except Exception as e:
                        print(f'{get_log_time()}> Failed to load server message: {e}')
            print(f'{get_log_time()}> Successfully loaded {self.FILE_PATH}')

    async def write_json_file(self):
        server_dicts = []
        for server in self.servers:
            server_dict = {
                "name": server.name,
                "address": server.address,
                "guild_id": server.guild.id,
                "channel_id": server.channel.id,
                "message_id": server.message.id
            }
            server_dicts.append(server_dict)
        with open(self.FILE_PATH, 'w') as json_file:
            json.dump(server_dicts, json_file, indent=4)
        print(f'{get_log_time()}> Successfully wrote {self.FILE_PATH}')

    async def setup_hook(self):
        await self.tree.sync()


def get_log_time():
    time = datetime.datetime.now().astimezone()
    output = ''
    if time.hour < 10:
        output += '0'
    output += f'{time.hour}:'
    if time.minute < 10:
        output += '0'
    output += f'{time.minute}:'
    if time.second < 10:
        output += '0'
    output += f'{time.second}'
    return output


def main():
    discord_token = os.getenv('DISCORD_TOKEN')
    intents = Intents.all()
    client = MCStatusClient(intents=intents)

    @client.event
    async def on_ready():
        if not client.servers:
            await client.read_json_file()
        if not poll_servers.is_running():
            poll_servers.start()
        print(f'{get_log_time()}> {client.user} has connected to Discord!')

    @tasks.loop(seconds=1)
    async def poll_servers():
        for server in client.servers:
            await server.get_status()

    @client.tree.command(name='addserver', description='Add a Minecraft server to track.')
    @app_commands.describe(ip='IP of the server to add', port='(Optional) Port of the server to add')
    async def addserver_command(interaction:Interaction, ip:str, name:str, port:int = 25565):
        address = f'{ip}:{port}'
        for server in client.servers:
            if server.address == address:
                message_link = f'https://discord.com/channels/{server.guild.id}/{server.channel.id}/{server.message.id}'
                embed = Embed(title='Status', description=f'[Go to Message]({message_link})', color=Color.blue())
                await interaction.response.send_message(f'This server is already added!', embed=embed)
                return
        server = MCServer(name, address)
        await server.make_message(interaction.channel)
        client.servers.append(server)
        await client.write_json_file()
        await interaction.response.send_message(f'__{server.name} Server Status__')

    @client.tree.command(name='removeserver', description='Remove a Minecraft server from tracking.')
    @app_commands.describe(ip='IP of the server to remove')
    async def removeserver_command(interaction:Interaction, ip:str):
        for server in client.servers.copy():
            if ip in server.address and server.message.channel.guild.id == interaction.guild.id:
                client.servers.remove(server)
                await interaction.response.send_message(f'Removed server!')
                return
        if not client.servers:
            response = f'There are no servers added.'
        else:
            response = f'Did not find server.\n\nExisting Servers:\n'
            for server in client.servers:
                response += f'{server.address}\n'
        await interaction.response.send_message(response)

    client.run(discord_token)


if __name__ == '__main__':
    main()
