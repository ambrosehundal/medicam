function initVideo(token, room, enableLocalVideo) {
	Twilio.Video.connect(token, {
		name: room,
		audio: true,
		video: enableLocalVideo,
		preferredVideoCodecs: ['VP8', 'H264']
	}).then(function(room) {
		console.log("Successfully joined a Room", room);

		room.localParticipant.tracks.forEach(function(publication) {
			if (publication.kind == "video") {
				var track = publication.track;
				var container = document.getElementById('local-media');
				setChildNode(container, track.attach());
			}
		});

		room.participants.forEach(function(participant) {
			console.log("Participant is connected to the Room", participant.identity);
			handleParticipant(participant);
			updateConnectionStatus(room);
		});

		room.on('participantConnected', function(participant) {
			console.log("A remote Participant connected", participant);
			handleParticipant(participant);
			updateConnectionStatus(room);
		});

		room.on('participantDisconnected', function(participant) {
  			console.log("Participant disconnected", participant.identity);
  			updateConnectionStatus(room);
		});

	}, function(error) {
		console.error("Unable to connect to Room", error.message);
		document.getElementById('connection-status').innerText = "Error";
	});
}

function updateConnectionStatus(room) {
	if (room.participants.size > 0) {
		document.getElementById('connection-status').innerText = "Connected";
	} else {
		document.getElementById('connection-status').innerText = "Disconnected";
	}
}

function setChildNode(parent, newChild) {
	var children = parent.childNodes;
	for (var i in children) {
		if (children.hasOwnProperty(i)) {
			var child = children[i];
			if (child.tagName == newChild.tagName) {
				parent.removeChild(child);
			}
		}
	}
	parent.appendChild(newChild);
}

function handleParticipant(participant) {
	var container = document.getElementById('remote-media');

	participant.tracks.forEach(function(publication) {
		if (publication.isSubscribed) {
			var track = publication.track;
			setChildNode(container, track.attach());
		}
	});

	participant.on('trackSubscribed', function(track) {
		setChildNode(container, track.attach());
	});
}

function showPreview() {
	Twilio.Video.createLocalVideoTrack().then(function(track) {
		var container = document.getElementById('local-media');
		setChildNode(container, track.attach());
	});
}
