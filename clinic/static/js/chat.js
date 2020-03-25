function initChat() {
	refreshChat();
	setTimeout(refreshChat, 5000);
}

function refreshChat() {
	var xhr = new XMLHttpRequest();
	xhr.onreadystatechange = function() {
		if (this.readyState == XMLHttpRequest.DONE) {
			if (this.status == 200) {
				handleChatResponse(JSON.parse(this.responseText));
			} else {
				console.error("chat error:", this.status, this.responseText);
			}
			setTimeout(function() { refreshChat() }, 5000);
		}
	};
	xhr.open("GET", "/clinic/chat/", true);
	xhr.send();
}

function shouldScrollToBottom(div) {
	if (Math.ceil(div.scrollHeight - div.scrollTop) === div.clientHeight) {
		return true; // scrolled to bottom
	} else if (div.scrollHeight <= div.clientHeight) {
		return true; // no scrollbar
	}
	return false;
}

function handleChatResponse(response) {
	var container = document.getElementById('chat-messages');
	var scrollToBottom = shouldScrollToBottom(container);

	for (i = 0; i < response.messages.length; i++) {
		var msg = response.messages[i];
		appendMessage(msg);
	}

	if (scrollToBottom) {
		container.scrollTop = container.scrollHeight;
	}
}

function appendMessage(msg) {
	var container = document.getElementById('chat-messages');
	var elemID = msg.uuid;
	var elem = document.getElementById(elemID);
	if (!!elem) { // already exists?
		return;
	}

	// convert timestamp to time string
	var d = new Date(msg.time);
	var time = ('0' + d.getHours()).slice(-2) + ":" + ('0' + d.getMinutes()).slice(-2) + ":" + ('0' + d.getSeconds()).slice(-2);

	elem = document.createElement('li');
	elem.id = elemID;
	elem.innerHTML = '<span class="name"></span><span class="time"></span><div class="text"></div>';
	elem.getElementsByClassName('name')[0].innerText = msg.name;
	elem.getElementsByClassName('time')[0].innerText = time;
	elem.getElementsByClassName('text')[0].innerText = msg.text;
	container.appendChild(elem);
}

function uuidv4() {
	return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
		var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
		return v.toString(16);
	});
}

function getCookie(cname) {
	var name = cname + "=";
	var decodedCookie = decodeURIComponent(document.cookie);
	var ca = decodedCookie.split(';');
	for (var i = 0; i <ca.length; i++) {
		var c = ca[i];
		while (c.charAt(0) == ' ') {
			c = c.substring(1);
		}
		if (c.indexOf(name) == 0) {
			return c.substring(name.length, c.length);
		}
	}
	return "";
}

function sendChatMessage() {
	var field = document.getElementById('send-message');
	var text = field.value;
	var uuid = uuidv4();

	if (text.length == 0) {
		return;
	}

	var xhr = new XMLHttpRequest();
	xhr.onreadystatechange = function() {
		//TODO: indicate success/failure
	};
	xhr.open("POST", "/clinic/chat/", true);
	xhr.setRequestHeader("Content-Type", "application/json");
	xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken'));
	xhr.send(JSON.stringify({"uuid": uuid, "text": text}));

	field.value = "";

	appendMessage({
		"uuid": uuid,
		"name": "You",
		"time": new Date().getTime(),
		"text": text
	});

	var container = document.getElementById('chat-messages');
	container.scrollTop = container.scrollHeight;
}
