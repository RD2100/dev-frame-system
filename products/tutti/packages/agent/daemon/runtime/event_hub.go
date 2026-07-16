package agentruntime

import (
	"strings"
	"sync"
)

type EventHub struct {
	mu          sync.Mutex
	subscribers map[string]map[*eventSubscriber]struct{}
}

func NewEventHub() *EventHub {
	return &EventHub{subscribers: make(map[string]map[*eventSubscriber]struct{})}
}

func (h *EventHub) Subscribe(roomID, agentSessionID string) (<-chan StreamEvent, func()) {
	return h.SubscribeWithInitial(roomID, agentSessionID, nil)
}

func (h *EventHub) SubscribeWithInitial(roomID, agentSessionID string, initial []StreamEvent) (<-chan StreamEvent, func()) {
	if h == nil {
		ch := make(chan StreamEvent)
		close(ch)
		return ch, func() {}
	}
	key := eventHubKey(roomID, agentSessionID)
	if key == "" {
		ch := make(chan StreamEvent)
		close(ch)
		return ch, func() {}
	}
	subscriber := newEventSubscriber()
	h.mu.Lock()
	if h.subscribers[key] == nil {
		h.subscribers[key] = make(map[*eventSubscriber]struct{})
	}
	h.subscribers[key][subscriber] = struct{}{}
	h.mu.Unlock()
	for _, event := range initial {
		subscriber.enqueue(event)
	}

	return subscriber.ch, func() {
		h.mu.Lock()
		if subscribers := h.subscribers[key]; subscribers != nil {
			delete(subscribers, subscriber)
			if len(subscribers) == 0 {
				delete(h.subscribers, key)
			}
		}
		h.mu.Unlock()
		subscriber.close()
	}
}

func (h *EventHub) Publish(roomID, agentSessionID string, events []StreamEvent) {
	if h == nil || len(events) == 0 {
		return
	}
	key := eventHubKey(roomID, agentSessionID)
	if key == "" {
		return
	}
	h.mu.Lock()
	subscribers := make([]*eventSubscriber, 0, len(h.subscribers[key]))
	for subscriber := range h.subscribers[key] {
		subscribers = append(subscribers, subscriber)
	}
	h.mu.Unlock()
	for _, event := range events {
		for _, subscriber := range subscribers {
			subscriber.enqueue(event)
		}
	}
}

type eventSubscriber struct {
	ch     chan StreamEvent
	done   chan struct{}
	wake   chan struct{}
	mu     sync.Mutex
	queue  []StreamEvent
	head   int
	closed bool
}

func newEventSubscriber() *eventSubscriber {
	subscriber := &eventSubscriber{
		ch:   make(chan StreamEvent, 64),
		done: make(chan struct{}),
		wake: make(chan struct{}, 1),
	}
	go subscriber.run()
	return subscriber
}

func (s *eventSubscriber) enqueue(event StreamEvent) {
	if s == nil {
		return
	}
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return
	}
	s.queue = append(s.queue, event)
	s.mu.Unlock()
	s.notify()
}

func (s *eventSubscriber) run() {
	defer close(s.ch)
	for {
		event, ok := s.next()
		if !ok {
			return
		}
		select {
		case s.ch <- event:
		case <-s.done:
			return
		}
	}
}

func (s *eventSubscriber) next() (StreamEvent, bool) {
	for {
		s.mu.Lock()
		if s.head < len(s.queue) {
			event := s.queue[s.head]
			s.queue[s.head] = StreamEvent{}
			s.head++
			s.compactQueueLocked()
			s.mu.Unlock()
			return event, true
		}
		if s.closed {
			s.mu.Unlock()
			return StreamEvent{}, false
		}
		s.mu.Unlock()

		select {
		case <-s.wake:
		case <-s.done:
			return StreamEvent{}, false
		}
	}
}

func (s *eventSubscriber) compactQueueLocked() {
	if s.head == 0 {
		return
	}
	if s.head == len(s.queue) {
		s.queue = s.queue[:0]
		s.head = 0
		return
	}
	if s.head < 64 || s.head*2 < len(s.queue) {
		return
	}
	copy(s.queue, s.queue[s.head:])
	s.queue = s.queue[:len(s.queue)-s.head]
	s.head = 0
}

func (s *eventSubscriber) close() {
	if s == nil {
		return
	}
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return
	}
	s.closed = true
	close(s.done)
	s.mu.Unlock()
	s.notify()
}

func (s *eventSubscriber) notify() {
	select {
	case s.wake <- struct{}{}:
	default:
	}
}

func eventHubKey(roomID, agentSessionID string) string {
	roomID = strings.TrimSpace(roomID)
	agentSessionID = strings.TrimSpace(agentSessionID)
	if roomID == "" || agentSessionID == "" {
		return ""
	}
	return roomID + "\x00" + agentSessionID
}
